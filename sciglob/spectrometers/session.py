"""Process-global AvaSpec DLL session.

The AvaSpec DLL is a single shared resource for every spectrometer in the
process. Two hard-won field lessons (spec section 6) motivate a single
serialization chokepoint:

* A ``StopMeasure`` issued on spectrometer A while spectrometer B is
  transferring data breaks the transfer (blick_spectrometer.py:1691-1692).
* The field code guarded the DLL with a boolean flag + 10 ms polling, which is
  race-prone; the rewrite doctrine (prompt.md:169-175) formalizes it as a real
  lock.

:class:`AvaSession` therefore owns a :class:`threading.RLock` and routes **every**
DLL call through :meth:`AvaSession._avs`. :func:`get_session` returns the
process-global singleton; tests construct their own :class:`AvaSession` with an
injected fake ``dll`` so the session logic runs hardware-free.
"""

import logging
import re
import sys
import threading
import time
from ctypes import byref, c_uint, sizeof
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sciglob.core.exceptions import SpectrometerError
from sciglob.spectrometers.errors import get_error_message
from sciglob.spectrometers.structures import AvsIdentityType

logger = logging.getLogger("sciglob.AvaSession")

# Validated DLL version family -- spec section 1. A mismatch WARNS, never refuses.
EXPECTED_DLL_VERSION = "9.14.0.0"

# AVS_Init(-27) ETHCONN_REUSE retry budget (doctrine prompt.md:169; spec section 14).
INIT_ETHCONN_RETRIES = 5
INIT_ETHCONN_GAP_S = 1.0

# AVS_Done can block forever if the DLL worker thread vanishes (spec section 4.4);
# guard the call with an external watchdog thread and this join timeout.
DONE_WATCHDOG_TIMEOUT_S = 10.0

# Settle after AVS_Done before AVS_Init during a Tier B session restart.
RESTART_SETTLE_S = 2.0

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")


def parse_dll_version(path: Optional[str]) -> str:
    """Extract a ``d.d.d.d`` version string from a DLL path, else ``""``.

    The field code identifies DLL versions by the containing directory name,
    e.g. ``.../Avaspec-DLL_9.14.0.0_64bits/avaspecx64.dll`` (spec section 1).
    """
    if not path:
        return ""
    match = _VERSION_RE.search(path)
    return match.group(1) if match else ""


@dataclass
class AvsIdentity:
    """Decoded view of an :class:`AvsIdentityType` returned by ``AVS_GetList``."""

    serial: str
    name: str
    status: int
    raw: AvsIdentityType  # standalone copy, safe to pass to AVS_Activate later

    @classmethod
    def from_struct(cls, struct: AvsIdentityType) -> "AvsIdentity":
        """Build from a DLL struct, decoding serial/name (spec section 4 step 7)."""
        # from_buffer_copy detaches from the (soon GC'd) enumeration array so the
        # raw identity stays valid when handed to AVS_Activate.
        raw = AvsIdentityType.from_buffer_copy(struct)
        serial = raw.SerialNumber.decode("utf-8", "ignore").strip("\x00").strip()
        name = raw.UserFriendlyName.decode("utf-8", "ignore").strip("\x00").strip()
        status_bytes = raw.Status
        status = status_bytes[0] if status_bytes else 0
        return cls(serial=serial, name=name, status=status, raw=raw)


class AvaSession:
    """Owns the shared AvaSpec DLL handle and the serialization chokepoint.

    Every DLL entry point is invoked through :meth:`_avs`, which holds
    :attr:`_lock` for the duration of the call. The DLL is loaded lazily on
    first use (or a fake ``dll`` may be injected for testing).

    Args:
        dll_path: Explicit path to ``avaspecx64.dll`` / ``avaspec.dll``.
            When ``None`` the path is auto-discovered on first load.
        dll: An already-loaded (or fake) DLL object. When provided, no real
            library is loaded -- this is the test injection point.
        sleep: Sleep function (injected as a no-op in tests to avoid real waits).
    """

    def __init__(
        self,
        dll_path: Optional[str] = None,
        dll: Optional[Any] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ):
        self._lock = threading.RLock()
        self._dll = dll
        self._dll_path = dll_path
        self._dll_version = "" if dll is None else "injected"
        self._initialized = False
        self._ndevices = 0
        self._sleep = sleep if sleep is not None else time.sleep
        # Reactivation callbacks for Tier B session restart (loosely coupled so
        # the session never imports the spectrometer class).
        self._channels: dict[object, Callable[[], None]] = {}
        self.logger = logger

    # -- DLL loading --------------------------------------------------------

    def _discover_dll_path(self) -> Optional[str]:
        """Best-effort search for the AvaSpec DLL (spec section 1).

        64-bit Python prefers ``avaspecx64.dll``; newest directory first.
        """
        import glob
        import os

        arch64 = sys.maxsize > 2**32
        dll_name = "avaspecx64.dll" if arch64 else "avaspec.dll"
        bases = []
        env = os.environ.get("SCIGLOB_AVASPEC_DLL")
        if env:
            if os.path.isfile(env):
                return env
            bases.append(env)
        bases += [
            r"C:\Blick\lib\oslib\spec_ava1",
            r"C:\Blick\src\devices",
            os.path.join(os.getcwd(), "oslib", "spec_ava1"),
        ]
        candidates: list[str] = []
        for base in bases:
            if os.path.isdir(base):
                candidates.extend(glob.glob(os.path.join(base, "**", dll_name), recursive=True))
        if arch64:
            # Prefer paths naming an x64 build; then newest by mtime.
            candidates.sort(key=lambda p: ("x64" in p.lower(), os.path.getmtime(p)), reverse=True)
        else:
            candidates.sort(key=os.path.getmtime, reverse=True)
        return candidates[0] if candidates else None

    def _load_dll(self) -> Any:
        """Load the real AvaSpec DLL via ``WinDLL`` (stdcall), version-warning only."""
        import ctypes

        path = self._dll_path or self._discover_dll_path()
        if path is None:
            raise SpectrometerError(
                "AvaSpec DLL (avaspecx64.dll) not found. Install the AvaSpec DLL and pass "
                "dll_path=, set SCIGLOB_AVASPEC_DLL, or use SimulatedSpectrometer "
                "(pip install sciglob[spectrometer])."
            )
        if sys.platform != "win32":
            raise SpectrometerError(
                "The Avantes driver requires the Windows AvaSpec DLL. Use "
                "SimulatedSpectrometer on non-Windows hosts."
            )
        version = parse_dll_version(path)
        if version and version != EXPECTED_DLL_VERSION:
            self.logger.warning(
                "AvaSpec DLL version %s != validated %s; proceeding anyway (spec section 1).",
                version,
                EXPECTED_DLL_VERSION,
            )
        try:
            # windll.LoadLibrary in the field code -> stdcall. Reloading an
            # already-loaded DLL returns the same handle (ava1_spectrometer.py:960).
            dll = ctypes.WinDLL(path)
        except OSError as exc:
            raise SpectrometerError(f"Failed to load AvaSpec DLL at {path}: {exc}") from exc
        self._dll_path = path
        self._dll_version = version or "unknown"
        self.logger.info("Loaded AvaSpec DLL %s (version %s)", path, self._dll_version)
        return dll

    def _ensure_dll(self) -> Any:
        if self._dll is None:
            self._dll = self._load_dll()
        return self._dll

    # -- THE chokepoint -----------------------------------------------------

    def _avs(self, fname: str, *args: Any) -> Any:
        """Invoke a single DLL function under the process-global lock.

        Every AvaSpec call in the library routes through here so that no two DLL
        entry points ever run concurrently (spec section 6).
        """
        with self._lock:
            dll = self._ensure_dll()
            fn = getattr(dll, fname)
            return fn(*args)

    # -- lifecycle ----------------------------------------------------------

    def init(self) -> int:
        """Idempotent ``AVS_Init(0)`` (USB). Returns the device count.

        Applies the doctrine's -27 ETHCONN_REUSE retry (5x @ 1 s) and the field
        fallback of ``AVS_Done`` then a single re-init on any other failure
        (spec section 4 step 3 and section 14).
        """
        with self._lock:
            if self._initialized:
                return self._ndevices
            ndev = self._init_once()
            self._initialized = True
            self._ndevices = ndev
            self.logger.info("AVS_Init succeeded: %d USB device(s)", ndev)
            return ndev

    def _try_init(self) -> int:
        try:
            return int(self._avs("AVS_Init", 0))  # 0 = USB connected devices
        except Exception as exc:  # noqa: BLE001 - never raise across the DLL boundary
            self.logger.error("AVS_Init raised: %s", exc)
            return -1

    def _init_once(self) -> int:
        ndev = self._try_init()
        if ndev > 0:
            return ndev
        # -27 ETHCONN_REUSE: retry up to 5x @ 1 s (doctrine prompt.md:169).
        attempts = 0
        while ndev == -27 and attempts < INIT_ETHCONN_RETRIES:
            self.logger.warning(
                "AVS_Init returned -27 (Ethernet reuse); retry %d/%d",
                attempts + 1,
                INIT_ETHCONN_RETRIES,
            )
            self._sleep(INIT_ETHCONN_GAP_S)
            ndev = self._try_init()
            attempts += 1
            if ndev > 0:
                return ndev
        # Field fallback: AVS_Done then a single re-init (blick_spectrometer.py:1231-1248).
        if ndev <= 0:
            self.logger.warning("AVS_Init failed (%d); calling AVS_Done and retrying once", ndev)
            try:
                self._avs("AVS_Done")
            except Exception as exc:  # noqa: BLE001
                self.logger.debug("AVS_Done during init fallback raised: %s", exc)
            ndev = self._try_init()
        if ndev <= 0:
            raise SpectrometerError(
                f"AVS_Init failed: {get_error_message(ndev)} (ndev={ndev})",
                error_code=ndev,
            )
        return ndev

    def done(self, timeout_s: float = DONE_WATCHDOG_TIMEOUT_S) -> None:
        """Call ``AVS_Done`` under an external watchdog (it can hang forever).

        The worker thread acquires the chokepoint lock and makes the call; this
        method never holds the lock across the (possibly hanging) join, so a
        wedged ``AVS_Done`` leaves the session marked uninitialized without
        deadlocking the caller (spec section 4.4).
        """
        with self._lock:
            if self._dll is None:
                self._initialized = False
                self._ndevices = 0
                return

        def _call() -> None:
            try:
                self._avs("AVS_Done")
            except Exception as exc:  # noqa: BLE001
                self.logger.error("AVS_Done raised: %s", exc)

        worker = threading.Thread(target=_call, name="AVS_Done-watchdog", daemon=True)
        worker.start()
        worker.join(timeout_s)
        if worker.is_alive():
            self.logger.error(
                "AVS_Done did not return within %.1fs (known DLL hang); abandoning the call.",
                timeout_s,
            )
        self._initialized = False
        self._ndevices = 0

    def enumerate(self) -> list[AvsIdentity]:
        """``AVS_UpdateUSBDevices`` + ``AVS_GetList`` -> decoded identities.

        Spec section 4 steps 5-6. Returns an empty list when no devices are
        present or the list cannot be retrieved (never raises for "none found").
        """
        with self._lock:
            ndev = int(self._avs("AVS_UpdateUSBDevices"))
            if ndev <= 0:
                return []
            arr = (AvsIdentityType * ndev)()
            required = c_uint(sizeof(AvsIdentityType) * ndev)
            count = int(self._avs("AVS_GetList", c_uint(sizeof(arr)), byref(required), byref(arr)))
            if count <= 0:
                return []
            return [AvsIdentity.from_struct(arr[i]) for i in range(min(count, ndev))]

    def restart(self) -> None:
        """Tier B session restart: quiesce all -> ``AVS_Done`` -> ``AVS_Init`` -> reactivate.

        Snapshots the registered reactivation callbacks, tears the DLL session
        down (with watchdog), re-initializes, then reactivates every channel.
        Callbacks run outside the lock so a channel's own ``connect`` can take it.
        """
        with self._lock:
            callbacks = list(self._channels.values())
        self.logger.warning("Tier B: restarting AvaSpec session (Done -> Init -> reactivate all)")
        self.done()
        self._sleep(RESTART_SETTLE_S)
        self.init()
        for callback in callbacks:
            try:
                callback()
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Channel reactivation after session restart failed: %s", exc)

    def dll_version(self) -> str:
        """Return the loaded DLL version (parsed from its path), else ``"unknown"``."""
        with self._lock:
            if self._dll_version:
                return self._dll_version
            if self._dll_path:
                self._dll_version = parse_dll_version(self._dll_path) or "unknown"
                return self._dll_version
            return "unknown"

    # -- channel registry (for Tier B reactivation) ------------------------

    def register_channel(self, reactivate: Callable[[], None]) -> object:
        """Register a reactivation callback; returns a token to unregister with."""
        token = object()
        with self._lock:
            self._channels[token] = reactivate
        return token

    def unregister_channel(self, token: Optional[object]) -> None:
        if token is None:
            return
        with self._lock:
            self._channels.pop(token, None)

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# -- process-global singleton ----------------------------------------------

_global_session: Optional[AvaSession] = None
_global_lock = threading.Lock()


def get_session(dll_path: Optional[str] = None, dll: Optional[Any] = None) -> AvaSession:
    """Return the process-global :class:`AvaSession`, creating it on first call.

    Args:
        dll_path: DLL path used only when the singleton is first created.
        dll: Fake/loaded DLL used only when the singleton is first created.
    """
    global _global_session
    with _global_lock:
        if _global_session is None:
            _global_session = AvaSession(dll_path=dll_path, dll=dll)
        return _global_session


def reset_global_session() -> None:
    """Drop the process-global session reference (test/teardown helper)."""
    global _global_session
    with _global_lock:
        _global_session = None

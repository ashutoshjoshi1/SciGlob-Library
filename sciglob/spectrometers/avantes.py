"""Avantes AvaSpec spectrometer driver (ctypes over the shared DLL session).

This is a ctypes-over-DLL driver, but it never loads the DLL itself: all calls
go through the injected/shared :class:`~sciglob.spectrometers.session.AvaSession`
chokepoint, so the module imports fine on a machine with no DLL and is fully
exercisable against a fake DLL or the :class:`SimulatedSpectrometer` twin.

Design (spec section 15):

* ``connect`` = Activate + config handshake (never ``AVS_Init`` -- the session
  owns init).
* ``disconnect`` = ``StopMeasure`` -> ``Deactivate`` (never ``AVS_Done``).
* Acquisition is a poll loop (``AVS_Measure`` in poll mode + ``AVS_PollScan`` +
  ``AVS_GetScopeData``) so every wait is a ``time.sleep`` slice with an optional
  user-supplied ``pump`` callback -- no wx/Qt.
* Recovery: Tier A (deactivate -> re-enumerate poll -> re-activate a fresh
  identity, never Done/Init); Tier B raises :class:`SessionRestartRequired`
  when ``AVS_Activate`` persistently returns 1000.
* Dead-handle guards: ``set_integration_time`` / ``measure`` / ``read_aux_sensor``
  / ``abort`` / ``read_data`` no-op cleanly when the device handle is ``None``.
"""

import logging
import math
import threading
import time
from array import array
from collections.abc import Sequence
from ctypes import byref, c_byte, c_double, c_float, c_uint, c_ushort
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from sciglob.core.exceptions import (
    SessionRestartRequired,
    SpectrometerError,
    TimeoutError,
)
from sciglob.spectrometers.errors import AVS_INVALID_HANDLE, get_error_message
from sciglob.spectrometers.session import AvaSession, AvsIdentity, get_session
from sciglob.spectrometers.structures import AvaDeviceType, MeasConfigType, devtype_name

try:  # numpy is optional (spec: return array('d')/list when absent)
    import numpy as _np
except ImportError:  # pragma: no cover - exercised on numpy-less CI
    _np = None  # type: ignore[assignment]

HAVE_NUMPY = _np is not None

# The cycle count is passed to AVS_Measure / AVS_MeasureCallback as a uint16
# (spec section 4.2). Values above this silently wrap in the DLL, so the driver
# rejects them up front.
MAX_CYCLES = 0xFFFF  # 65535

# Device families that support AVS_ResetDevice (wedge cure) -- spec section 11.1.
_RESETTABLE_DEVTYPES = frozenset(
    {AvaDeviceType.TYPE_AS7010, AvaDeviceType.TYPE_AS7007, AvaDeviceType.TYPE_ASMINI}
)


def make_counts(values: Sequence[float]) -> Any:
    """Wrap counts as a numpy float64 array if numpy is present, else ``array('d')``.

    Returns ``Any`` deliberately: the concrete type depends on whether numpy is
    installed, and callers treat it as a length-able, indexable sequence.
    """
    if HAVE_NUMPY:
        return _np.asarray(values, dtype="float64")
    return array("d", [float(v) for v in values])


def _poly_eval(coeffs: Sequence[float], x: float) -> float:
    """Evaluate a polynomial given ascending-order coefficients (Horner)."""
    result = 0.0
    for coefficient in reversed(list(coeffs)):
        result = result * x + coefficient
    return result


def _coerce_devtype(value: Optional[Union[int, AvaDeviceType]]) -> Optional[AvaDeviceType]:
    if value is None:
        return None
    if isinstance(value, AvaDeviceType):
        return value
    try:
        return AvaDeviceType(int(value))
    except ValueError:
        return AvaDeviceType.TYPE_UNKNOWN


@dataclass
class RecoveryPolicy:
    """Recovery budgets and caps in one place (spec sections 7, 11 and 14).

    The Tier A/B budgets (re-enumeration poll/budget, settle, activate attempts
    and gap) are the doctrine values (prompt.md:171-173, spec section 14); the
    remaining timings are field-observed (spec section 7).
    """

    # Tier A / B budgets (doctrine, spec section 14)
    reenum_poll_s: float = 2.0
    budget_s: float = 90.0
    first_connect_budget_s: float = 45.0
    settle_s: float = 5.0
    activate_attempts: int = 5
    activate_gap_s: float = 2.5
    stage2_max_visits: int = 5
    power_cycles_max: int = 15
    alarm_rate: tuple[int, int] = (4, 30 * 60)  # >=4 recoveries in 30 min

    # Field-observed timings (spec section 7)
    pre_activate_settle_s: float = 0.5  # blick_spectrometer.py:1312
    post_activate_settle_s: float = 0.2  # ava1_spectrometer.py:462
    it_handshake_settle_s: float = 0.2  # ava1_spectrometer.py:546
    stop_measure_settle_s: float = 0.2  # blick_spectrometer.py:2205
    reset_settle_s: float = 5.0  # ava1_spectrometer.py:2062 (AVS_ResetDevice)
    data_arrival_margin_s: float = 35.0  # op.maxwaits[6], blick_osparams.py:70
    per_cycle_margin_ms: float = 5.0  # watchdog.py:37-61 (5 ms/cycle)
    poll_slice_s: float = 0.01  # DLL-busy poll granularity, spec section 6


@dataclass
class Spectrum:
    """A measured spectrum and its acquisition metadata.

    Attributes:
        counts: Per-pixel counts (numpy float64 array, or ``array('d')``/list).
            For multi-cycle measurements this is the per-pixel mean over the
            non-saturated cycles.
        wavelengths: Per-pixel wavelengths (nm) or ``None`` if unavailable.
        timestamps: Per-cycle arrival times in seconds (10 us ticks -> s).
        it_ms: Integration time used, in milliseconds.
        ncy_requested / ncy_handled / ncy_saturated: cycle bookkeeping.
        saturated: True if any cycle saturated (host-side check, spec section 8).
        data_ok: False if a cycle failed the per-cycle consistency check
            (saturation, negative counts, or NaN -- spec section 8).
    """

    counts: Any
    wavelengths: Any
    timestamps: list[float]
    it_ms: float
    ncy_requested: int
    ncy_handled: int
    ncy_saturated: int = 0
    saturated: bool = False
    data_ok: bool = True

    def __len__(self) -> int:
        return len(self.counts)


class AvantesSpectrometer:
    """Driver for a single AvaSpec spectrometer over the shared DLL session.

    Args:
        serial: Target serial number (``None`` -> first enumerated device).
        dll_path: DLL path, used only if a shared session must be created.
        session: An :class:`AvaSession` to use (defaults to the process-global
            singleton). Tests inject a session backed by a fake DLL.
        npixels: Configured active pixel count; a device mismatch is a hard error.
        min_it_ms / max_it_ms / it_resolution_ms: integration-time limits and
            quantization step (spec section 9).
        device_type: Known device family (else read via ``AVS_GetDeviceType``).
        discriminator_factor: Host-side count scaling (default 4.0, spec section 8).
        nbits: ADC bit depth for the saturation limit ``2**nbits - 1``.
        recovery_policy: Budgets/caps (defaults to :class:`RecoveryPolicy`).
        sleep: Sleep function (injected as a no-op in tests).
    """

    def __init__(
        self,
        serial: Optional[str] = None,
        dll_path: Optional[str] = None,
        session: Optional[AvaSession] = None,
        npixels: int = 2048,
        *,
        min_it_ms: float = 2.4,
        max_it_ms: float = 4000.0,
        it_resolution_ms: Optional[float] = None,
        device_type: Optional[Union[int, AvaDeviceType]] = None,
        discriminator_factor: float = 4.0,
        nbits: int = 16,
        recovery_policy: Optional[RecoveryPolicy] = None,
        name: str = "Avantes",
        sleep: Optional[Callable[[float], None]] = None,
    ):
        self.name = name
        self.logger = logging.getLogger("sciglob.Avantes")
        self._serial = serial
        self._npixels = int(npixels)
        self._session = session if session is not None else get_session(dll_path=dll_path)
        self._min_it_ms = float(min_it_ms)
        self._max_it_ms = float(max_it_ms)
        self._it_resolution_ms = it_resolution_ms
        self._device_type = _coerce_devtype(device_type)
        self._discriminator_factor = float(discriminator_factor)
        self._saturation_limit = float(2**nbits - 1)  # spec section 8
        self.policy = recovery_policy or RecoveryPolicy()
        self._sleep = sleep if sleep is not None else time.sleep

        self._lock = threading.RLock()
        # spec_id IS the device handle returned by AVS_Activate. The *DLL* handle
        # is owned by the session; mark_power_cycled() clears spec_id but keeps
        # the shared DLL loaded (spec section 12).
        self._spec_id: Optional[int] = None
        self._connected = False
        self._it_ms = self._min_it_ms
        self._config: Optional[MeasConfigType] = None
        self._wavelengths: Any = None
        self._pending_ncy = 0
        self._abort_on_saturation = True
        self._data_since_last_recovery = False
        self._session_token: Optional[object] = None

    # -- properties ---------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected and self._spec_id is not None

    @property
    def serial(self) -> Optional[str]:
        return self._serial

    @property
    def integration_time_ms(self) -> float:
        return self._it_ms

    @property
    def device_type(self) -> Optional[AvaDeviceType]:
        return self._device_type

    @property
    def wavelengths(self) -> Any:
        """Per-pixel wavelengths (nm), cached at connect; ``None`` if unavailable."""
        return self._wavelengths

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> None:
        """Activate the device and run the config handshake (spec section 4).

        Never calls ``AVS_Init`` -- the session owns initialization. It does ask
        the session to ``init()`` (idempotent) so standalone use works.
        """
        with self._lock:
            if self._connected and self._spec_id is not None:
                self.logger.warning("%s already connected", self.name)
                return
            self._session.init()  # idempotent; the ONLY place AVS_Init is reached
            identity = self._resolve_identity()
            self._activate(identity.raw)
            self._post_activate_setup()
            self._connected = True
            if self._session_token is None:
                self._session_token = self._session.register_channel(self._reactivate)
            self.logger.info(
                "Connected to Avantes %s (handle=%s, devtype=%s)",
                self._serial,
                self._spec_id,
                devtype_name(self._device_type) if self._device_type is not None else "?",
            )

    def disconnect(self) -> None:
        """``StopMeasure`` -> ``Deactivate`` (never ``AVS_Done``) -- spec section 4.4."""
        with self._lock:
            if self._spec_id is not None:
                self.abort(ignore_errors=True)
                self._deactivate(ignore_errors=True)
            self._connected = False
            self._session.unregister_channel(self._session_token)
            self._session_token = None

    def mark_power_cycled(self) -> None:
        """Invalidate the device handle before an external relay USB power-cycle.

        Clears ``spec_id`` (the device handle) but keeps the shared DLL loaded
        (spec section 12/14). Every guarded method no-ops until reconnected.
        """
        with self._lock:
            self.logger.info("Marking %s power-cycled; invalidating device handle", self._serial)
            self._spec_id = None
            self._connected = False
            self._data_since_last_recovery = False

    def __enter__(self) -> "AvantesSpectrometer":
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    # -- connect internals --------------------------------------------------

    def _resolve_identity(self) -> AvsIdentity:
        identities = self._session.enumerate()
        if not identities:
            raise SpectrometerError("No AvaSpec devices enumerated")
        if self._serial is None:
            return identities[0]
        for identity in identities:
            if identity.serial == self._serial:
                return identity
        found = [identity.serial for identity in identities]
        raise SpectrometerError(f"AvaSpec serial {self._serial!r} not found; enumerated: {found}")

    def _activate(self, identity_struct: Any) -> int:
        # Legacy pre-activate settle for slow USB2 ports (blick_spectrometer.py:1312).
        self._sleep(self.policy.pre_activate_settle_s)
        handle = int(self._session._avs("AVS_Activate", byref(identity_struct)))
        if handle == AVS_INVALID_HANDLE:
            raise SpectrometerError(
                "AVS_Activate returned invalid handle (1000)", error_code=AVS_INVALID_HANDLE
            )
        self._spec_id = handle
        self._sleep(self.policy.post_activate_settle_s)  # spec section 7
        return handle

    def _post_activate_setup(self) -> None:
        """Config handshake after Activate (spec section 4 steps 11-15)."""
        self._verify_pixels()
        if self._device_type is None:
            self._device_type = self._read_device_type()
        # Spec might still be measuring from a previous session (step 11).
        self.abort(ignore_errors=True)
        self._config = self._build_baseline_config()
        # IT sanity handshake: set 2*min then min "to check IT change works" (step 15).
        self.set_integration_time(2 * self._min_it_ms)
        self.set_integration_time(self._min_it_ms)
        self._sleep(self.policy.it_handshake_settle_s)
        self._wavelengths = self._read_wavelengths()

    def _verify_pixels(self) -> None:
        npix = c_ushort(0)
        self._session._avs("AVS_GetNumPixels", self._spec_id, byref(npix))
        if npix.value and npix.value != self._npixels:
            raise SpectrometerError(
                f"Pixel count mismatch: device reports {npix.value}, configured "
                f"{self._npixels}. Check IOF parameters."
            )

    def _read_device_type(self) -> Optional[AvaDeviceType]:
        dtype = c_byte(0)
        try:
            self._session._avs("AVS_GetDeviceType", self._spec_id, byref(dtype))
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("AVS_GetDeviceType failed: %s", exc)
            return None
        return _coerce_devtype(dtype.value)

    def _build_baseline_config(self) -> MeasConfigType:
        """Baseline MeasConfigType (spec section 4 step 14)."""
        cfg = MeasConfigType()
        cfg.m_StartPixel = 0
        cfg.m_StopPixel = self._npixels - 1
        # m_IntegrationDelay = round(6*(l_NanoSec+20.84)/125), l_NanoSec=-21 -> 0.
        l_nanosec = -21.0
        cfg.m_IntegrationDelay = int(round(6.0 * (l_nanosec + 20.84) / 125.0))
        cfg.m_NrAverages = 1
        cfg.m_CorDynDark_m_Enable = 0
        cfg.m_CorDynDark_m_ForgetPercentage = 0
        cfg.m_Smoothing_m_SmoothPix = 0
        cfg.m_Smoothing_m_SmoothModel = 0
        cfg.m_SaturationDetection = 0  # saturation is host-side (spec section 8)
        cfg.m_Trigger_m_Mode = 0
        cfg.m_Trigger_m_Source = 0
        cfg.m_Trigger_m_SourceType = 0
        cfg.m_Control_m_StrobeControl = 0
        cfg.m_Control_m_LaserDelay = 0
        cfg.m_Control_m_LaserWidth = 0
        cfg.m_Control_m_LaserWaveLength = 0.0
        cfg.m_Control_m_StoreToRam = 0
        cfg.m_IntegrationTime = c_float(self._it_ms)
        return cfg

    def _read_wavelengths(self) -> Any:
        """Wavelength array via ``AVS_GetLambda`` (spec section 14); ``None`` if absent."""
        if self._spec_id is None:
            return None
        buf = (c_double * self._npixels)()
        try:
            self._session._avs("AVS_GetLambda", self._spec_id, byref(buf))
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("AVS_GetLambda unavailable (%s); wavelengths unknown", exc)
            return None
        return make_counts([buf[i] for i in range(self._npixels)])

    # -- configuration ------------------------------------------------------

    def _clamp_quantize(self, it_ms: float) -> float:
        value = max(self._min_it_ms, min(self._max_it_ms, float(it_ms)))
        if self._it_resolution_ms:
            step = self._it_resolution_ms
            value = round(value / step) * step
            value = max(self._min_it_ms, min(self._max_it_ms, value))
        return value

    def set_integration_time(self, it_ms: float) -> None:
        """Clamp + quantize the integration time and push it via ``AVS_PrepareMeasure``.

        Dead-handle guard: no-ops if the device handle is ``None`` (spec section 12).
        """
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("set_integration_time ignored: no active handle")
                return
            if self._config is None:
                self._config = self._build_baseline_config()
            clamped = self._clamp_quantize(it_ms)
            self._config.m_IntegrationTime = c_float(clamped)
            result = int(
                self._session._avs("AVS_PrepareMeasure", self._spec_id, byref(self._config))
            )
            if result != 0:
                raise SpectrometerError(
                    f"AVS_PrepareMeasure failed: {get_error_message(result)}", error_code=result
                )
            self._it_ms = clamped

    # -- acquisition --------------------------------------------------------

    @staticmethod
    def _check_ncycles(ncycles: int) -> int:
        """Validate the cycle count against the DLL's uint16 range (spec section 4.2).

        AVS_Measure / AVS_MeasureCallback take the cycle count as a ``c_uint16``;
        values above 65535 would silently wrap, so they are rejected here.
        """
        ncy = int(ncycles)
        if ncy < 1 or ncy > MAX_CYCLES:
            raise ValueError(
                f"ncycles={ncy} out of range: must be 1..{MAX_CYCLES} "
                f"(passed to the DLL as a uint16)."
            )
        return ncy

    def start(
        self,
        ncycles: int = 1,
        *,
        store_to_ram: bool = False,
        abort_on_saturation: bool = True,
    ) -> None:
        """Start a non-blocking measurement in poll mode (spec section 4.2).

        Uses ``AVS_Measure(handle, 0, ncycles)`` (window handle 0 => poll mode)
        so :meth:`wait` can drive it with plain ``time.sleep`` slices.
        Dead-handle guard: no-ops if the handle is ``None``.

        Raises:
            ValueError: if ``ncycles`` is outside the uint16 range the DLL
                accepts (1..65535, spec section 4.2).
            NotImplementedError: if ``store_to_ram`` is requested -- this
                poll-mode driver does not wire the StoreToRam callback path.
        """
        ncy = self._check_ncycles(ncycles)
        if store_to_ram:
            raise NotImplementedError(
                "store_to_ram is not supported by this poll-mode driver: it "
                "requires the AVS_MeasureCallback RAM path (set_store_to_ram_ncy "
                "+ PrepareMeasure, ncy=1 to MeasureCallback -- spec section 4.2)."
            )
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("start ignored: no active handle")
                return
            self._pending_ncy = ncy
            self._abort_on_saturation = abort_on_saturation
            result = int(self._session._avs("AVS_Measure", self._spec_id, 0, ncy))
            if result != 0:
                raise SpectrometerError(
                    f"AVS_Measure failed: {get_error_message(result)}", error_code=result
                )

    def _poll_scan(self) -> int:
        # AVS_PollScan: 1 = data available, 0 = not yet, <0 = error (spec section 4.3).
        return int(self._session._avs("AVS_PollScan", self._spec_id))

    def _read_scope_raw(self) -> tuple[list[float], int]:
        time_label = c_uint(0)
        buf = (c_double * self._npixels)()
        result = int(
            self._session._avs("AVS_GetScopeData", self._spec_id, byref(time_label), byref(buf))
        )
        if result != 0:
            raise SpectrometerError(get_error_message(result), error_code=result)
        # Host-side discriminator scaling (spec section 8).
        counts = [buf[i] * self._discriminator_factor for i in range(self._npixels)]
        return counts, int(time_label.value)

    def _compute_timeout(self, ncy: int) -> float:
        per_cycle_s = (self._it_ms + self.policy.per_cycle_margin_ms) / 1000.0
        return ncy * per_cycle_s + self.policy.data_arrival_margin_s

    def wait(
        self,
        timeout_s: Optional[float] = None,
        pump: Optional[Callable[[], None]] = None,
    ) -> Optional[Spectrum]:
        """Poll until all cycles arrive, then return the accumulated :class:`Spectrum`.

        Waits are ``time.sleep`` slices; ``pump`` (if given) is called on each
        idle slice so a GUI event loop can be serviced without importing wx/Qt.
        Dead-handle guard: returns ``None`` if the handle is ``None``.

        Raises:
            TimeoutError: if data does not arrive within the (computed) budget.
            SpectrometerError: if ``AVS_PollScan`` reports a DLL error.
        """
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("wait ignored: no active handle")
                return None
            ncy = self._pending_ncy
            it_ms = self._it_ms
            abort_on_saturation = self._abort_on_saturation

        budget = timeout_s if timeout_s is not None else self._compute_timeout(ncy)
        deadline = time.monotonic() + budget
        npix = self._npixels
        accum = [0.0] * npix
        handled = 0
        sat_cycles = 0
        saturated = False
        data_ok = True
        timestamps: list[float] = []

        while handled < ncy:
            status = self._poll_scan()
            if status == 1:
                counts, ticks = self._read_scope_raw()
                arrival_s = ticks * 1e-5  # 10 us ticks -> s (spec section 4.3)
                self._data_since_last_recovery = True
                # Per-cycle consistency check (spec section 8): NaN and negative
                # counts are corrupt cycles -- warn, mark data not-ok, and abort
                # like saturation.
                if any(math.isnan(c) for c in counts):
                    self.logger.warning(
                        "NaN counts detected !!! aborting measurement "
                        "(ncy=%d, handled=%d)",
                        ncy,
                        handled,
                    )
                    data_ok = False
                    timestamps.append(arrival_s)
                    self.abort(ignore_errors=True)
                    break
                if counts and min(counts) < 0.0:
                    self.logger.warning(
                        "negative counts detected !!! aborting measurement "
                        "(ncy=%d, handled=%d, min=%g)",
                        ncy,
                        handled,
                        min(counts),
                    )
                    data_ok = False
                    timestamps.append(arrival_s)
                    self.abort(ignore_errors=True)
                    break
                peak = max(counts) if counts else 0.0
                if peak >= self._saturation_limit:
                    # Host-side saturation: drop the cycle; abort through the loop.
                    saturated = True
                    data_ok = False
                    sat_cycles += 1
                    timestamps.append(arrival_s)
                    if abort_on_saturation:
                        self.abort(ignore_errors=True)
                        break
                    continue
                for i in range(npix):
                    accum[i] += counts[i]
                handled += 1
                timestamps.append(arrival_s)
            elif status == 0:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Data arrival timeout after {budget:.1f}s "
                        f"(ncy={ncy}, IT={it_ms}ms, handled={handled})"
                    )
                if pump is not None:
                    try:
                        pump()
                    except Exception as exc:  # noqa: BLE001
                        self.logger.debug("pump callback raised: %s", exc)
                self._sleep(self.policy.poll_slice_s)
            else:
                raise SpectrometerError(get_error_message(status), error_code=status)

            if handled < ncy and time.monotonic() > deadline:
                raise TimeoutError(
                    f"Data arrival timeout after {budget:.1f}s "
                    f"(ncy={ncy}, IT={it_ms}ms, handled={handled})"
                )

        denom = handled if handled else 1
        mean = [value / denom for value in accum]
        return Spectrum(
            counts=make_counts(mean),
            wavelengths=self._wavelengths,
            timestamps=timestamps,
            it_ms=it_ms,
            ncy_requested=ncy,
            ncy_handled=handled,
            ncy_saturated=sat_cycles,
            saturated=saturated,
            data_ok=data_ok,
        )

    def measure(
        self,
        ncycles: int = 1,
        *,
        store_to_ram: bool = False,
        abort_on_saturation: bool = True,
        timeout_s: Optional[float] = None,
        pump: Optional[Callable[[], None]] = None,
    ) -> Optional[Spectrum]:
        """Blocking sugar over :meth:`start` + :meth:`wait`.

        Dead-handle guard: returns ``None`` if the handle is ``None``.

        Raises:
            ValueError: if ``ncycles`` is outside the uint16 range (spec section 4.2).
            NotImplementedError: if ``store_to_ram`` is requested (spec section 4.2).
        """
        # Argument validation happens before the dead-handle guard so a bad
        # ncycles / unsupported store_to_ram is a hard error, never a silent None.
        self._check_ncycles(ncycles)
        if store_to_ram:
            raise NotImplementedError(
                "store_to_ram is not supported by this poll-mode driver: it "
                "requires the AVS_MeasureCallback RAM path (set_store_to_ram_ncy "
                "+ PrepareMeasure, ncy=1 to MeasureCallback -- spec section 4.2)."
            )
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("measure ignored: no active handle")
                return None
        self.start(ncycles, store_to_ram=store_to_ram, abort_on_saturation=abort_on_saturation)
        return self.wait(timeout_s=timeout_s, pump=pump)

    def abort(self, ignore_errors: bool = True) -> None:
        """``AVS_StopMeasure`` + settle. Dead-handle guard: no-op if handle is ``None``."""
        with self._lock:
            if self._spec_id is None:
                self.logger.debug("abort no-op: no active handle")
                return
            try:
                self._session._avs("AVS_StopMeasure", self._spec_id)
                self._sleep(self.policy.stop_measure_settle_s)
            except Exception as exc:  # noqa: BLE001
                if not ignore_errors:
                    raise
                self.logger.error("AVS_StopMeasure error: %s", exc)

    def read_data(self) -> Optional[tuple[Any, float]]:
        """Read the last scope data directly. Dead-handle guard: ``None`` if no handle.

        Returns:
            ``(counts, arrival_time_s)`` or ``None`` when there is no active handle.
        """
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("read_data ignored: no active handle")
                return None
            counts, ticks = self._read_scope_raw()
            return make_counts(counts), ticks * 1e-5

    def _deactivate(self, ignore_errors: bool = False) -> None:
        if self._spec_id is None:
            return
        try:
            self._session._avs("AVS_Deactivate", self._spec_id)
        except Exception as exc:  # noqa: BLE001
            if not ignore_errors:
                raise
            self.logger.error("AVS_Deactivate error: %s", exc)
        finally:
            # Deactivate always clears the handle (ava1_spectrometer.py:1487).
            self._spec_id = None

    # -- auxiliary sensors --------------------------------------------------

    def read_aux_sensor(self, analogid: int) -> Optional[float]:
        """Read an analog input voltage via ``AVS_GetAnalogIn`` (spec section 10).

        Dead-handle guard: returns ``None`` if the handle is ``None`` or the read
        fails.
        """
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("read_aux_sensor ignored: no active handle")
                return None
            volts = c_float(0.0)
            try:
                result = int(
                    self._session._avs(
                        "AVS_GetAnalogIn", self._spec_id, c_byte(analogid), byref(volts)
                    )
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("AVS_GetAnalogIn(%d) raised: %s", analogid, exc)
                return None
            if result != 0:
                self.logger.warning(
                    "AVS_GetAnalogIn(%d) failed: %s", analogid, get_error_message(result)
                )
                return None
            return float(volts.value)

    def detector_temperature(self) -> float:
        """Detector temperature via ``AVS_GetAnalogIn(0)`` (spec section 10).

        Poly ``T = 58.7 - 20.48*V``; returns ``-99.0`` on failure or ``V >= 5.0``.
        """
        volts = self.read_aux_sensor(0)
        if volts is None or volts >= 5.0:
            return -99.0
        return _poly_eval([58.7, -20.48], volts)

    def board_temperature(self) -> float:
        """Board temperature via ``AVS_GetAnalogIn(6)`` (spec section 10).

        Digital boards (AS7007/AS7010) report degrees C directly (poly ``[0, 1]``,
        vcut 99.0); analog boards use the quartic poly (vcut 5.0). Returns
        ``-99.0`` on failure or when the voltage exceeds its validity cut.
        """
        volts = self.read_aux_sensor(6)
        if volts is None:
            return -99.0
        if self._device_type in (AvaDeviceType.TYPE_AS7007, AvaDeviceType.TYPE_AS7010):
            if volts >= 99.0:
                return -99.0
            return _poly_eval([0.0, 1.0], volts)
        if volts >= 5.0:
            return -99.0
        return _poly_eval([118.69, -70.361, 21.02, -3.6443, 0.1993], volts)

    # -- recovery -----------------------------------------------------------

    def _poll_for_identity(self, budget_s: float) -> Optional[AvsIdentity]:
        deadline = time.monotonic() + budget_s
        while True:
            try:
                for identity in self._session.enumerate():
                    if self._serial is None or identity.serial == self._serial:
                        return identity
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("enumerate during recovery failed: %s", exc)
            if time.monotonic() >= deadline:
                return None
            self._sleep(self.policy.reenum_poll_s)

    def _tier_a_recover(self) -> bool:
        """Tier A recovery: deactivate -> re-enumerate poll -> re-activate.

        NEVER calls ``AVS_Done`` or ``AVS_Init`` (spec section 11.1/14). On
        persistent ``AVS_Activate == 1000`` this escalates to Tier B, which
        raises :class:`SessionRestartRequired`.

        Returns:
            True if a fresh handle was activated and the device re-set-up.

        Raises:
            SessionRestartRequired: Tier B escalation on persistent invalid handle.
        """
        with self._lock:
            self.logger.warning(
                "Tier A recovery for %s (deactivate -> re-enumerate -> re-activate; "
                "never Done/Init)",
                self._serial,
            )
            self._data_since_last_recovery = False
            self._deactivate(ignore_errors=True)
            identity = self._poll_for_identity(self.policy.budget_s)
            if identity is None:
                self.logger.error(
                    "Tier A: %s did not re-enumerate within %.0fs",
                    self._serial,
                    self.policy.budget_s,
                )
                return False
            self._sleep(self.policy.settle_s)
            for attempt in range(self.policy.activate_attempts):
                handle = int(self._session._avs("AVS_Activate", byref(identity.raw)))
                if handle != AVS_INVALID_HANDLE:
                    self._spec_id = handle
                    self._sleep(self.policy.post_activate_settle_s)
                    self._post_activate_setup()
                    self._connected = True
                    self.logger.info("Tier A recovery succeeded (handle=%s)", handle)
                    return True
                self.logger.warning(
                    "Tier A: AVS_Activate attempt %d/%d returned 1000",
                    attempt + 1,
                    self.policy.activate_attempts,
                )
                self._sleep(self.policy.activate_gap_s)
            # Persistent invalid handle -> Tier B.
            self._tier_b_escalate()
            return False  # unreachable: _tier_b_escalate raises

    def _tier_b_escalate(self) -> None:
        """Tier B: raise :class:`SessionRestartRequired` (spec section 11/14)."""
        message = (
            f"Avantes {self._serial}: AVS_Activate persistently returned 1000 after "
            f"{self.policy.activate_attempts} Tier A attempts; session restart required "
            f"(quiesce all channels, AVS_Done -> AVS_Init, reactivate)."
        )
        self.logger.error(message)
        raise SessionRestartRequired(message)

    def _wedge_cure(self) -> bool:
        """Wedge cure: single ``AVS_ResetDevice`` + 5 s settle (spec section 11.1).

        Gated on "no data arrived since the last recovery" (prompt.md:173): if a
        spectrum has arrived since the last recovery the wedge is not persistent,
        so the reboot is skipped. Only AS7010/AS7007/AS-MINI support the reset.

        Returns:
            True if a reset was issued and returned OK; False if skipped/unsupported.
        """
        with self._lock:
            if self._spec_id is None:
                self.logger.debug("wedge cure no-op: no active handle")
                return False
            if self._data_since_last_recovery:
                self.logger.info(
                    "Wedge cure skipped: data arrived since last recovery (prompt.md:173)"
                )
                return False
            if self._device_type not in _RESETTABLE_DEVTYPES:
                self.logger.warning(
                    "Wedge cure: AVS_ResetDevice unsupported on %s",
                    devtype_name(self._device_type) if self._device_type is not None else "?",
                )
                return False
            self.logger.warning(
                "Wedge cure: issuing AVS_ResetDevice (single retry) + %.0fs settle",
                self.policy.reset_settle_s,
            )
            try:
                result = int(self._session._avs("AVS_ResetDevice", self._spec_id))
            except Exception as exc:  # noqa: BLE001
                self.logger.error("AVS_ResetDevice raised: %s", exc)
                return False
            self._sleep(self.policy.reset_settle_s)
            self._data_since_last_recovery = False
            return result == 0

    def _reactivate(self) -> None:
        """Reactivate after a Tier B session restart (invoked by the session)."""
        with self._lock:
            try:
                identity = self._resolve_identity()
                self._activate(identity.raw)
                self._post_activate_setup()
                self._connected = True
                self.logger.info("Reactivated %s after session restart", self._serial)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Reactivation of %s failed: %s", self._serial, exc)

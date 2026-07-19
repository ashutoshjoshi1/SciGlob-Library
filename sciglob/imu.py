"""x-IMU3 head IMU integration (optional extra: ``sciglob[imu]``).

The x-IMU3 is a **push-based** device: it is *never* polled. The vendor SDK
(``ximu3``) owns the port and a background receive thread and delivers messages
via callbacks. This module registers callbacks, stores the latest sample and a
per-message-type counter under a lock, and exposes a non-blocking snapshot to
readers (spec §3 doctrine, tracker.py:5-8).

The per-message-type counters are the "connected-but-silent" diagnostic: a
connection can open with ``RESULT_OK`` and stream nothing (wrong firmware config,
device asleep). Counting messages per stream makes that state visible -- the
unit 071/999 silent-stream lesson (spec §4).

Design for testability WITHOUT ``ximu3``: :class:`ImuBackend` is a small ABC.
:class:`RealImuBackend` wraps the vendor SDK; :class:`SimulatedIMU` emits
scripted messages so tests run hardware-free. :class:`IMU` takes a backend
(default: the real backend when ``ximu3`` is importable).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sciglob.core.exceptions import ImuError

# ximu3 is an optional vendor dependency. Guard the import (spec §0/brief §"Optional
# dependency modules"): keep the module importable with zero extras, and only raise
# ImuError when the *real* backend is actually requested. Binding the module to an
# ``Any``-typed name keeps mypy clean across the vendor boundary.
try:  # pragma: no cover - exercised only when the extra is installed
    import ximu3 as _ximu3
except ImportError:  # pragma: no cover
    _ximu3 = None  # type: ignore[assignment]

ximu3: Any = _ximu3
HAS_XIMU3: bool = ximu3 is not None

logger = logging.getLogger("sciglob.IMU")

# --- Wire / SDK constants (all cited to the xIMU3 spec) ---------------------
DEFAULT_BAUD = 115200  # spec §1.1, §10 (all sources agree: 115200 8N1)
DEFAULT_RTS_CTS = False  # spec §1.1 (default off everywhere)
USB_SCAN_POLL_S = 0.25  # spec §1.2, §10 (PortScanner poll period)
USB_SCAN_TIMEOUT_S = 5.0  # spec §1.2, §10 (auto-scan give-up)
EULER_STALE_S = 0.75  # spec §5, §10 (quaternion->Euler fallback staleness window)
STREAMING_WINDOW_S = 1.0  # spec §4/§10 (rate-display window; health = orientation seen recently)

# Per-stream message types tracked by the counters (spec §4).
MESSAGE_TYPES = ("euler", "quaternion", "temperature", "battery")

Callback = Callable[[Any], None]


# --- Simulated message shapes ----------------------------------------------
# Attribute names mirror the ximu3 message objects consumed in the field source
# (spec §2.3) so the same IMU callbacks work against real and simulated backends.
@dataclass(frozen=True)
class EulerMessage:
    """xIMU3 EulerAngles message (spec §2.3): degrees, timestamp in microseconds."""

    timestamp: int
    roll: float
    pitch: float
    yaw: float


@dataclass(frozen=True)
class TemperatureMessage:
    """xIMU3 Temperature message (spec §2.3): degrees Celsius."""

    timestamp: int
    temperature: float


@dataclass(frozen=True)
class BatteryMessage:
    """xIMU3 Battery message (spec §2.3): percentage, volts, charging enum."""

    timestamp: int
    percentage: float
    voltage: float = 0.0
    charging_status: int = 0


@dataclass(frozen=True)
class QuaternionMessage:
    """xIMU3 Quaternion message (spec §2.3): normalised w,x,y,z.

    Provides :meth:`to_euler_angles_message` mirroring the SDK method used for
    the quaternion->Euler fallback (spec §5).
    """

    timestamp: int
    w: float
    x: float
    y: float
    z: float

    def to_euler_angles_message(self) -> EulerMessage:
        """Convert to Euler angles (ZYX / roll-pitch-yaw, degrees)."""
        w, x, y, z = self.w, self.x, self.y, self.z
        # roll (x-axis rotation)
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        # pitch (y-axis rotation), clamped to avoid domain errors near the poles
        sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
        pitch = math.asin(sinp)
        # yaw (z-axis rotation)
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return EulerMessage(
            timestamp=self.timestamp,
            roll=math.degrees(roll),
            pitch=math.degrees(pitch),
            yaw=math.degrees(yaw),
        )


# --- Backend abstraction ----------------------------------------------------
class ImuBackend(ABC):
    """Transport backend for :class:`IMU`.

    A backend owns exactly one host connection to one device. It opens the
    connection (verifying ``RESULT_OK``), lets the :class:`IMU` register
    push callbacks per message type, and closes cleanly.
    """

    @abstractmethod
    def open(self) -> None:
        """Open the connection. Must verify ``RESULT_OK`` / raise :class:`ImuError`."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection. Must be idempotent and swallow teardown errors."""

    @abstractmethod
    def register(self, message_type: str, callback: Callback) -> bool:
        """Register a push callback for ``message_type``.

        Returns True if the callback was registered, False if the backend/SDK
        build does not support this stream (registration is defensive -- older
        firmware simply never fires an unsupported callback; spec §2.1).
        """


class RealImuBackend(ImuBackend):
    """Backend wrapping the vendor ``ximu3`` SDK (spec §1, §2.1).

    Connects via explicit serial port (``SerialConnectionConfig(port, 115200,
    rts_cts)``) or, when no port is given, USB auto-scan
    (``PortScanner.scan_filter(PORT_TYPE_USB)``) polled every 0.25 s until a
    timeout. Callbacks are registered defensively via ``getattr`` so a firmware
    or SDK build missing one stream does not stop the others (spec §2.1).
    """

    # Generic message-type -> ximu3 Python SDK adder method (spec §2.1).
    _SDK_ADDERS = {
        "euler": "add_euler_angles_callback",
        "quaternion": "add_quaternion_callback",
        "temperature": "add_temperature_callback",
        "battery": "add_battery_callback",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baud: int = DEFAULT_BAUD,
        rts_cts: bool = DEFAULT_RTS_CTS,
        scan_timeout: float = USB_SCAN_TIMEOUT_S,
    ) -> None:
        if ximu3 is None:
            raise ImuError(
                "The xIMU3 backend was requested but the 'ximu3' package is not "
                "installed. Install it with: pip install sciglob[imu]"
            )
        self._port = port
        self._baud = baud
        self._rts_cts = rts_cts
        self._scan_timeout = scan_timeout
        self._connection: Any = None
        self._lock = threading.RLock()

    def _resolve_config(self) -> Any:
        """Build a connection config: explicit serial, else USB auto-scan (spec §1.1-1.2)."""
        if self._port:
            # spec §1.1: SerialConnectionConfig(port, baud, rts_cts)
            return ximu3.SerialConnectionConfig(self._port, self._baud, self._rts_cts)
        # spec §1.2: USB auto-scan loop, 0.25 s poll until timeout.
        deadline = time.monotonic() + self._scan_timeout
        while True:
            devices = ximu3.PortScanner.scan_filter(ximu3.PORT_TYPE_USB)
            if devices:
                return devices[0].connection_config
            if time.monotonic() >= deadline:
                raise ImuError("No xIMU3 USB device found during scan")
            time.sleep(USB_SCAN_POLL_S)

    def open(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            conn = ximu3.Connection(self._resolve_config())
            # spec §1.3: tolerate both SDK styles -- some raise, some return a code.
            try:
                result = conn.open()
            except Exception as exc:  # noqa: BLE001 - vendor SDK raises opaque errors
                raise ImuError(f"Could not open xIMU3 connection: {exc}") from exc
            if isinstance(result, int) and result != ximu3.RESULT_OK:
                raise ImuError(
                    f"Could not open xIMU3 connection: {ximu3.result_to_string(result)}"
                )
            self._connection = conn

    def register(self, message_type: str, callback: Callback) -> bool:
        conn = self._connection
        if conn is None:
            return False
        adder_name = self._SDK_ADDERS.get(message_type)
        if adder_name is None:
            return False
        # Defensive: skip if this SDK build lacks the method (spec §2.1).
        adder = getattr(conn, adder_name, None)
        if adder is None:
            return False
        try:
            adder(callback)
            return True
        except Exception:  # noqa: BLE001 - registration must never be fatal
            logger.warning("Failed to register '%s' callback", message_type, exc_info=True)
            return False

    def close(self) -> None:
        with self._lock:
            conn = self._connection
            self._connection = None
        # spec §9.2: close outside the lock the SDK callbacks may take.
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - teardown is best-effort
                logger.warning("Error closing xIMU3 connection", exc_info=True)


class SimulatedIMU(ImuBackend):
    """Hardware-free backend that emits scripted xIMU3 messages.

    Register callbacks via :class:`IMU`, then drive the streams with
    :meth:`push_euler` / :meth:`push_quaternion` / :meth:`push_temperature` /
    :meth:`push_battery`. Each push synchronously invokes the registered
    callback with a message object shaped like the vendor SDK's.
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, Callback] = {}
        self._is_open = False
        self._ts = 0

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def register(self, message_type: str, callback: Callback) -> bool:
        self._callbacks[message_type] = callback
        return True

    def _next_ts(self) -> int:
        # Monotonic microsecond stamps, like the device (spec §2.3).
        self._ts += 1000
        return self._ts

    def _emit(self, message_type: str, message: Any) -> None:
        cb = self._callbacks.get(message_type)
        if cb is not None:
            cb(message)

    def push_euler(
        self,
        roll: float,
        pitch: float,
        yaw: float,
        timestamp: Optional[int] = None,
    ) -> None:
        """Emit an EulerAngles message (degrees)."""
        ts = self._next_ts() if timestamp is None else timestamp
        self._emit("euler", EulerMessage(ts, roll, pitch, yaw))

    def push_quaternion(
        self,
        w: float,
        x: float,
        y: float,
        z: float,
        timestamp: Optional[int] = None,
    ) -> None:
        """Emit a Quaternion message (normalised)."""
        ts = self._next_ts() if timestamp is None else timestamp
        self._emit("quaternion", QuaternionMessage(ts, w, x, y, z))

    def push_temperature(self, temperature: float, timestamp: Optional[int] = None) -> None:
        """Emit a Temperature message (degrees Celsius)."""
        ts = self._next_ts() if timestamp is None else timestamp
        self._emit("temperature", TemperatureMessage(ts, temperature))

    def push_battery(
        self,
        percentage: float,
        voltage: float = 0.0,
        timestamp: Optional[int] = None,
    ) -> None:
        """Emit a Battery message (percent, volts)."""
        ts = self._next_ts() if timestamp is None else timestamp
        self._emit("battery", BatteryMessage(ts, percentage, voltage))


# --- IMU device -------------------------------------------------------------
class IMU:
    """x-IMU3 head IMU.

    Push-based, never polled: callbacks store the most recent sample and bump a
    per-message-type counter under a lock; readers snapshot without blocking the
    SDK thread (spec §3, §4). Requires ``pip install sciglob[imu]`` for the real
    backend; tests inject a :class:`SimulatedIMU` backend.

    Mounting convention (spec §6): Euler **roll** is the zenith axis, Euler
    **yaw** is the azimuth axis.

    Example:
        >>> backend = SimulatedIMU()
        >>> with IMU(backend=backend) as imu:
        ...     backend.push_euler(10.0, 0.0, 45.0)
        ...     imu.get_readings()["Roll"]
        10.0
    """

    def __init__(
        self,
        port: Optional[str] = None,
        backend: Optional[ImuBackend] = None,
        *,
        baud: int = DEFAULT_BAUD,
        rts_cts: bool = DEFAULT_RTS_CTS,
        scan_timeout: float = USB_SCAN_TIMEOUT_S,
        zenith_sign: int = 1,
        streaming_window_s: float = STREAMING_WINDOW_S,
    ) -> None:
        """Initialise the IMU.

        Args:
            port: Explicit serial port. Ignored when ``backend`` is supplied.
                When None and using the real backend, USB auto-scan is used.
            backend: Transport backend. When None, a :class:`RealImuBackend` is
                built (which raises :class:`ImuError` telling the user to
                ``pip install sciglob[imu]`` if ``ximu3`` is missing).
            baud: Serial baud rate (default 115200; spec §1.1).
            rts_cts: RTS/CTS flow control (default off; spec §1.1).
            scan_timeout: USB auto-scan give-up in seconds (spec §1.2).
            zenith_sign: Sign applied when mapping roll->zenith. Configurable per
                rig wiring (spec §6.2); default +1 (direct roll->zenith mapping).
            streaming_window_s: Freshness window for :attr:`is_streaming`.

        Raises:
            ImuError: If the real backend is requested but ``ximu3`` is missing.
        """
        self.logger = logging.getLogger("sciglob.IMU")
        # Per-device lock guarding latest values + counters + stream state (spec §3).
        self._lock = threading.RLock()

        if backend is not None:
            self._backend: ImuBackend = backend
        else:
            # Real backend requested by default -- raises ImuError if ximu3 missing.
            self._backend = RealImuBackend(
                port=port, baud=baud, rts_cts=rts_cts, scan_timeout=scan_timeout
            )

        self._zenith_sign = zenith_sign
        self._streaming_window_s = streaming_window_s

        # Shared state (guarded by self._lock).
        self._roll: Optional[float] = None
        self._pitch: Optional[float] = None
        self._yaw: Optional[float] = None
        self._temperature: Optional[float] = None
        self._battery: Optional[float] = None
        self._counts: dict[str, int] = {mt: 0 for mt in MESSAGE_TYPES}
        self._last_orientation_monotonic: Optional[float] = None
        self._last_euler_monotonic: Optional[float] = None
        self._open = False

    # --- lifecycle ----------------------------------------------------------
    def open(self) -> None:
        """Open the backend (verifying ``RESULT_OK``) and register callbacks.

        Idempotent: a second call while already open is a no-op.
        """
        with self._lock:
            if self._open:
                return
        # spec §1.3: backend.open() verifies RESULT_OK / raises ImuError.
        self._backend.open()
        # Register push callbacks defensively (spec §2.1). Order: euler, then
        # quaternion (fallback), temperature, battery.
        self._backend.register("euler", self._on_euler)
        self._backend.register("quaternion", self._on_quaternion)
        self._backend.register("temperature", self._on_temperature)
        self._backend.register("battery", self._on_battery)
        with self._lock:
            self._open = True

    def close(self) -> None:
        """Close the backend. Idempotent; teardown errors are swallowed."""
        with self._lock:
            self._open = False
        try:
            self._backend.close()
        except Exception:  # noqa: BLE001 - teardown is best-effort
            self.logger.warning("Error closing IMU backend", exc_info=True)

    def __enter__(self) -> "IMU":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    # --- push callbacks (invoked on the SDK background thread) --------------
    def _on_euler(self, message: Any) -> None:
        now = time.monotonic()
        with self._lock:
            self._counts["euler"] += 1
            self._roll = float(message.roll)
            self._pitch = float(message.pitch)
            self._yaw = float(message.yaw)
            self._last_euler_monotonic = now
            self._last_orientation_monotonic = now

    def _on_quaternion(self, message: Any) -> None:
        now = time.monotonic()
        # Convert outside the lock; store only if device Euler is stale (spec §5).
        euler: Optional[EulerMessage] = None
        try:
            euler = message.to_euler_angles_message()
        except Exception:  # noqa: BLE001 - conversion is best-effort
            self.logger.debug("Quaternion->Euler conversion failed", exc_info=True)
        with self._lock:
            self._counts["quaternion"] += 1
            self._last_orientation_monotonic = now
            euler_fresh = (
                self._last_euler_monotonic is not None
                and (now - self._last_euler_monotonic) < EULER_STALE_S
            )
            # Prefer device Euler; fall back to quaternion-derived only when the
            # Euler stream is absent or stale (spec §5, 750 ms window).
            if euler is not None and not euler_fresh:
                self._roll = float(euler.roll)
                self._pitch = float(euler.pitch)
                self._yaw = float(euler.yaw)

    def _on_temperature(self, message: Any) -> None:
        with self._lock:
            self._counts["temperature"] += 1
            self._temperature = float(message.temperature)

    def _on_battery(self, message: Any) -> None:
        with self._lock:
            self._counts["battery"] += 1
            self._battery = float(message.percentage)

    # --- data access (never blocks the SDK thread) -------------------------
    def get_readings(self) -> dict[str, Optional[float]]:
        """Return a snapshot of the latest values.

        Returns:
            Dict with keys ``Roll``, ``Pitch``, ``Yaw`` (degrees), ``Temp``
            (degrees Celsius) and ``Battery`` (percent). Any value not yet
            received is None.
        """
        with self._lock:
            return {
                "Roll": self._roll,
                "Pitch": self._pitch,
                "Yaw": self._yaw,
                "Temp": self._temperature,
                "Battery": self._battery,
            }

    def message_counts(self) -> dict[str, int]:
        """Return per-message-type counters (the connected-but-silent diagnostic).

        Returns:
            Dict with a count for each of ``euler``, ``quaternion``,
            ``temperature`` and ``battery`` (spec §4).
        """
        with self._lock:
            return dict(self._counts)

    def to_zenith_azimuth(self) -> tuple[Optional[float], Optional[float]]:
        """Map the latest orientation to (zenith, azimuth) in degrees.

        Mounting convention (spec §6): roll->zenith, yaw->azimuth. The zenith
        sign is configurable via ``zenith_sign`` (spec §6.2).

        Returns:
            ``(zenith, azimuth)``; either element is None if not yet received.
        """
        with self._lock:
            roll = self._roll
            yaw = self._yaw
        zenith = None if roll is None else self._zenith_sign * roll
        azimuth = yaw
        return (zenith, azimuth)

    @property
    def is_streaming(self) -> bool:
        """True only if orientation counters are advancing.

        Health check (spec §4): connected AND an orientation message (euler or
        quaternion) arrived within ``streaming_window_s``. A 0 Hz reading while
        "connected" is the connected-but-silent signature.
        """
        with self._lock:
            last = self._last_orientation_monotonic
            total = self._counts["euler"] + self._counts["quaternion"]
        if total == 0 or last is None:
            return False
        return (time.monotonic() - last) < self._streaming_window_s

    @property
    def is_open(self) -> bool:
        """Whether :meth:`open` has completed and :meth:`close` has not run."""
        with self._lock:
            return self._open

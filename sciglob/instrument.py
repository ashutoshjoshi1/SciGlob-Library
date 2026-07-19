"""Top-level instrument facade — talk to every device with a few lines of code.

``Instrument`` opens a complete Pandora-class hardware suite from a single YAML
config (or programmatically), degrades gracefully when a device is unplugged,
wires the cross-device couplings (relay/head-sensor spectrometer power-cycle
marking), and reports a per-device status map.

Example::

    from sciglob import Instrument

    inst = Instrument.from_yaml("pandora101.yaml")
    with inst:                                   # opens everything it finds
        inst.tracker.move_to(zenith=45.0, azimuth=180.0)
        inst.filter_wheel_1.set_filter("U340")
        inst.spectrometer.set_integration_time(200)   # ms
        spectrum = inst.spectrometer.measure(10)       # 10 accumulated cycles
        rh = inst.sbhs.get_humidity()
        inst.head_sensor.spec_power_cycle(1)     # auto-coordinates with the spectrometer
        print(inst.status())                     # per-device connected/simulated/error map

Design contract (see docs/RELIABILITY.md §5):

* A device that fails to open never sinks the whole instrument. Per ``strict``:
  ``strict=False`` (default) falls back to a simulated twin where one exists
  (else ``None``); ``strict=True`` re-raises the first open failure.
* Per-device open errors are collected in :attr:`errors` and surfaced by
  :meth:`status`.
* ``simulated=True`` builds every device as its simulated twin (no hardware).
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import yaml

logger = logging.getLogger("sciglob.Instrument")


class DeviceState(str, Enum):
    """Per-device state in an :class:`Instrument`."""

    CONNECTED = "connected"
    SIMULATED = "simulated"
    ABSENT = "absent"
    ERROR = "error"


@dataclass
class DeviceStatus:
    """Status record for one device slot."""

    name: str
    state: DeviceState
    error: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"state": self.state.value}
        if self.error:
            d["error"] = self.error
        if self.detail:
            d["detail"] = self.detail
        return d


class Instrument:
    """Facade over a full Pandora-class instrument.

    Attributes are populated per config: ``head_sensor``, ``tracker`` (head-sensor
    or direct-RS485 backend), ``filter_wheel_1``/``filter_wheel_2``, ``shadowband``,
    ``temperature_controllers`` (list), ``humidity_sensor``, ``gps``, ``sbhs``,
    ``asb``, ``srb``, ``relay_board``, ``spectrometer`` (or ``spectrometers`` list),
    ``camera``, ``imu``. Any slot may be ``None`` when absent and not simulated.
    """

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        *,
        strict: bool = False,
        simulated: bool = False,
    ):
        """Create an instrument from a config dict (does not open devices yet).

        Args:
            config: Nested config dict (see module docstring / ``from_yaml``).
            strict: Re-raise the first device-open failure instead of degrading.
            simulated: Build every device as its simulated twin (no hardware).
        """
        self.config = config or {}
        self.strict = strict
        self.simulated = simulated

        self.errors: dict[str, str] = {}
        self._status: dict[str, DeviceStatus] = {}
        self._opened = False

        # Device slots
        self.head_sensor: Any = None
        self.tracker: Any = None
        self.filter_wheel_1: Any = None
        self.filter_wheel_2: Any = None
        self.shadowband: Any = None
        self.temperature_controllers: list[Any] = []
        self.humidity_sensor: Any = None
        self.gps: Any = None
        self.sbhs: Any = None
        self.asb: Any = None
        self.srb: Any = None
        self.relay_board: Any = None
        self.spectrometers: list[Any] = []
        self.camera: Any = None
        self.imu: Any = None

        # Shared Avantes session (created lazily when a real spectrometer opens)
        self._ava_session: Any = None

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    @classmethod
    def from_yaml(cls, filepath: str, **kwargs: Any) -> "Instrument":
        """Build (but do not open) an instrument from a YAML config file."""
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(config=data, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any], **kwargs: Any) -> "Instrument":
        """Build (but do not open) an instrument from a config dict."""
        return cls(config=data, **kwargs)

    @classmethod
    def from_iof(cls, filepath: str, **kwargs: Any) -> "Instrument":
        """Build an instrument from a Pandora Instrument Operation File (IOF).

        A thin importer that maps IOF serial assignments onto the native config
        schema. IOF field mapping mirrors NewBlick ``blick_io.py`` /
        Pandora2.0 ``serial_assignment_from_iof``; only the serial-port
        assignments and device types are consumed here.
        """
        from sciglob.config.iof import config_from_iof

        return cls(config=config_from_iof(filepath), **kwargs)

    @property
    def spectrometer(self) -> Any:
        """The first spectrometer (convenience for single-spec instruments)."""
        return self.spectrometers[0] if self.spectrometers else None

    @property
    def is_open(self) -> bool:
        """True once :meth:`open` has run."""
        return self._opened

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def open(self) -> "Instrument":
        """Open every configured device, degrading gracefully.

        Returns:
            self (for chaining / context-manager use)

        Raises:
            Any device error only when ``strict=True``.
        """
        if self._opened:
            return self

        self._open_head_sensor()
        self._open_tracker()
        self._open_temperature_controllers()
        self._open_humidity_sensor()
        self._open_gps()
        self._open_sbhs()
        self._open_asb()
        self._open_srb()
        self._open_relay_board()
        self._open_spectrometers()
        self._open_camera()
        self._open_imu()
        self._wire_couplings()

        self._opened = True
        return self

    def close(self) -> None:
        """Close every open device, swallowing per-device close errors."""
        slots: list[Any] = [
            self.head_sensor,
            self.tracker if self.tracker is not self.head_sensor else None,
            self.humidity_sensor,
            self.gps,
            self.sbhs,
            self.asb,
            self.srb,
            self.relay_board,
            self.camera,
            self.imu,
            *self.temperature_controllers,
            *self.spectrometers,
        ]
        for dev in slots:
            if dev is None:
                continue
            for method in ("disconnect", "close", "release", "stop"):
                fn = getattr(dev, method, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception as e:  # pragma: no cover - defensive
                        logger.warning("Error closing %r: %s", dev, e)
                    break
        if self._ava_session is not None:
            try:
                self._ava_session.done()
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Error closing Avantes session: %s", e)
        self._opened = False

    def __enter__(self) -> "Instrument":
        return self.open()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    def status(self) -> dict[str, Any]:
        """Return the per-device connected / simulated / error map."""
        return {name: st.to_dict() for name, st in self._status.items()}

    def _record(
        self,
        name: str,
        state: DeviceState,
        error: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        self._status[name] = DeviceStatus(name, state, error, detail or {})
        if error:
            self.errors[name] = error

    # ------------------------------------------------------------------ #
    # Per-device open helpers
    # ------------------------------------------------------------------ #

    def _try(
        self,
        name: str,
        build_real,
        build_sim=None,
        *,
        present: bool = True,
    ) -> Any:
        """Open one device with graceful degradation.

        Args:
            name: Slot name (for status/errors).
            build_real: Zero-arg callable returning a connected real device.
            build_sim: Zero-arg callable returning a simulated device, or None.
            present: Whether the device is configured at all.
        """
        if not present:
            self._record(name, DeviceState.ABSENT)
            return None

        if self.simulated:
            if build_sim is None:
                self._record(name, DeviceState.ABSENT)
                return None
            dev = build_sim()
            self._record(name, DeviceState.SIMULATED)
            return dev

        try:
            dev = build_real()
            self._record(name, DeviceState.CONNECTED)
            return dev
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            logger.warning("Device '%s' failed to open: %s", name, msg)
            if self.strict:
                raise
            if build_sim is not None:
                try:
                    dev = build_sim()
                    self._record(name, DeviceState.SIMULATED, error=msg)
                    return dev
                except Exception as e2:  # pragma: no cover - defensive
                    self._record(name, DeviceState.ERROR, error=f"{msg}; sim: {e2}")
                    return None
            self._record(name, DeviceState.ERROR, error=msg)
            return None

    @staticmethod
    def _serial_kwargs(section: dict[str, Any]) -> dict[str, Any]:
        serial = section.get("serial", {}) or {}
        out: dict[str, Any] = {}
        if "port" in serial:
            out["port"] = serial["port"]
        if "baudrate" in serial:
            out["baudrate"] = serial["baudrate"]
        return out

    def _open_head_sensor(self) -> None:
        present = self.config.get("head_sensor") is not None
        section: dict[str, Any] = self.config.get("head_sensor") or {}

        def build_real() -> Any:
            from sciglob.devices.head_sensor import HeadSensor

            kw = self._serial_kwargs(section)
            for key in (
                "sensor_type",
                "tracker_type",
                "degrees_per_step",
                "motion_limits",
                "home_position",
                "fw1_filters",
                "fw2_filters",
            ):
                if key in section:
                    kw[key] = section[key]
            hs = HeadSensor(**kw)
            hs.connect()
            return hs

        def build_sim() -> Any:
            from sciglob.devices.head_sensor import SimulatedHeadSensor

            kw: dict[str, Any] = {}
            if present:
                if "sensor_type" in section:
                    kw["sensor_type"] = section["sensor_type"]
                if "tracker_type" in section:
                    kw["tracker_type"] = section["tracker_type"]
            return SimulatedHeadSensor(**kw)

        self.head_sensor = self._try(
            "head_sensor", build_real, build_sim, present=present
        )
        # Expose the head-sensor children as convenience slots.
        if self.head_sensor is not None:
            self.filter_wheel_1 = self.head_sensor.filter_wheel_1
            self.filter_wheel_2 = self.head_sensor.filter_wheel_2
            self.shadowband = self.head_sensor.shadowband

    def _open_tracker(self) -> None:
        """Choose the tracking backend: head-sensor (default) or direct RS-485."""
        section = self.config.get("tracker") or {}
        backend = str(section.get("backend", "head_sensor")).lower()

        if backend in ("rs485", "oriental", "azd", "az"):
            def build_real() -> Any:
                from sciglob.devices.rs485_tracker import RS485Tracker

                kw = self._serial_kwargs(section)
                for key in (
                    "zenith_slave",
                    "azimuth_slave",
                    "zenith_steps_per_deg",
                    "azimuth_steps_per_deg",
                ):
                    if key in section:
                        kw[key] = section[key]
                trk = RS485Tracker(**kw)
                trk.connect()
                return trk

            def build_sim() -> Any:
                from sciglob.devices.rs485_tracker import SimulatedRS485Tracker

                trk = SimulatedRS485Tracker()
                trk.connect()
                return trk

            self.tracker = self._try("tracker", build_real, build_sim, present=True)
        else:
            # Head-sensor tracking: reuse the head-sensor's tracker child.
            if self.head_sensor is not None:
                self.tracker = self.head_sensor.tracker
                self._record("tracker", self._status["head_sensor"].state)
            else:
                self._record("tracker", DeviceState.ABSENT)

    def _open_temperature_controllers(self) -> None:
        specs = self.config.get("temperature_controllers")
        if specs is None:
            # Back-compat single-controller keys.
            singles = [
                self.config.get("temperature_controller_1"),
                self.config.get("temperature_controller_2"),
            ]
            specs = [s for s in singles if s is not None]
        if not specs:
            self._record("temperature_controllers", DeviceState.ABSENT)
            return

        from sciglob.devices.temperature_controller import TemperatureController

        for i, section in enumerate(specs):
            name = f"temperature_controller_{i + 1}"
            ctype = section.get("controller_type", "TETech1")

            def build_real(section=section) -> Any:
                kw = self._serial_kwargs(section)
                if "controller_type" in section:
                    kw["controller_type"] = section["controller_type"]
                tc = TemperatureController(**kw)
                tc.connect()
                return tc

            def build_sim(ctype=ctype, i=i) -> Any:
                # A hardware-free twin exists for the TETech1090 framing.
                from sciglob.devices.temperature_controller import (
                    SimulatedTemperatureController1090,
                )

                if str(ctype) != "TETech1090":
                    raise NotImplementedError(
                        f"No simulated twin for controller_type {ctype!r}"
                    )
                return SimulatedTemperatureController1090(port=f"SIM_TEC1090_{i}")

            dev = self._try(name, build_real, build_sim, present=True)
            if dev is not None:
                self.temperature_controllers.append(dev)

    def _open_humidity_sensor(self) -> None:
        present = self.config.get("humidity_sensor") is not None
        section: dict[str, Any] = self.config.get("humidity_sensor") or {}

        def build_real() -> Any:
            from sciglob.devices.humidity_sensor import HumiditySensor

            hs = HumiditySensor(**self._serial_kwargs(section))
            hs.connect()
            return hs

        self.humidity_sensor = self._try(
            "humidity_sensor", build_real, None, present=present
        )

    def _open_gps(self) -> None:
        present = self.config.get("gps") is not None
        section: dict[str, Any] = self.config.get("gps") or {}

        def build_real() -> Any:
            from sciglob.devices.positioning import GlobalSatGPS, NovatelGPS

            system = str(section.get("system_type", "GlobalSat"))
            cls = NovatelGPS if system.lower().startswith("nova") else GlobalSatGPS
            gps = cls(**self._serial_kwargs(section))
            gps.connect()
            return gps

        self.gps = self._try("gps", build_real, None, present=present)

    def _open_sbhs(self) -> None:
        present = self.config.get("sbhs") is not None
        section: dict[str, Any] = self.config.get("sbhs") or {}

        def build_real() -> Any:
            from sciglob.devices.sbhs import SBHS

            kw = self._serial_kwargs(section)
            if present and "device_id" in section:
                kw["device_id"] = section["device_id"]
            dev = SBHS(**kw)
            dev.connect()
            return dev

        def build_sim() -> Any:
            from sciglob.devices.sbhs import SimulatedSBHS

            dev = SimulatedSBHS()
            dev.connect()
            return dev

        self.sbhs = self._try("sbhs", build_real, build_sim, present=present)

    def _open_asb(self) -> None:
        present = self.config.get("asb") is not None
        section: dict[str, Any] = self.config.get("asb") or {}

        def build_real() -> Any:
            from sciglob.devices.asb import ASB

            kw = self._serial_kwargs(section)
            if present and "device_id" in section:
                kw["device_id"] = section["device_id"]
            dev = ASB(**kw)
            dev.connect()
            return dev

        def build_sim() -> Any:
            from sciglob.devices.asb import SimulatedASB

            dev = SimulatedASB()
            dev.connect()
            return dev

        self.asb = self._try("asb", build_real, build_sim, present=present)

    def _open_srb(self) -> None:
        present = self.config.get("srb") is not None
        section: dict[str, Any] = self.config.get("srb") or {}

        def build_real() -> Any:
            from sciglob.devices.srb import SRB

            dev = SRB(**self._serial_kwargs(section))
            dev.connect()
            return dev

        def build_sim() -> Any:
            from sciglob.devices.srb import SimulatedSRB

            dev = SimulatedSRB()
            dev.connect()
            return dev

        self.srb = self._try("srb", build_real, build_sim, present=present)

    def _open_relay_board(self) -> None:
        present = self.config.get("relay_board") is not None
        section: dict[str, Any] = self.config.get("relay_board") or {}

        def build_real() -> Any:
            from sciglob.devices.relay_board import RelayBoard

            kw = self._serial_kwargs(section)
            if "nrelays" in section:
                kw["nrelays"] = section["nrelays"]
            board = RelayBoard(**kw)
            board.connect()
            return board

        def build_sim() -> Any:
            from sciglob.devices.relay_board import SimulatedRelayBoard

            nrelays = section.get("nrelays", 4) if present else 4
            return SimulatedRelayBoard(nrelays=nrelays)

        self.relay_board = self._try(
            "relay_board", build_real, build_sim, present=present
        )

    def _open_spectrometers(self) -> None:
        section = self.config.get("spectrometer")
        if section is None:
            section = self.config.get("spectrometers")
        if section is None:
            self._record("spectrometer", DeviceState.ABSENT)
            return

        specs = section if isinstance(section, list) else [section]

        for i, sp in enumerate(specs):
            name = "spectrometer" if len(specs) == 1 else f"spectrometer_{i + 1}"

            def build_real(sp=sp) -> Any:
                from sciglob.spectrometers import AvantesSpectrometer, get_session

                if self._ava_session is None:
                    self._ava_session = get_session()
                    self._ava_session.init()
                dev = AvantesSpectrometer(
                    serial=str(sp.get("serial_number") or sp.get("serial") or ""),
                    dll_path=sp.get("dll_path"),
                    session=self._ava_session,
                    npixels=sp.get("npixels", 2048),
                )
                dev.connect()
                return dev

            def build_sim(sp=sp) -> Any:
                from sciglob.spectrometers import SimulatedSpectrometer

                dev = SimulatedSpectrometer(
                    serial=str(sp.get("serial_number") or sp.get("serial") or "SIM"),
                    npixels=sp.get("npixels", 2048),
                )
                dev.connect()
                return dev

            dev = self._try(name, build_real, build_sim, present=True)
            if dev is not None:
                self.spectrometers.append(dev)

    def _open_camera(self) -> None:
        present = self.config.get("camera") is not None
        section: dict[str, Any] = self.config.get("camera") or {}

        def build_real() -> Any:
            from sciglob.camera import Camera

            kw: dict[str, Any] = {}
            for key in ("backend", "index", "resolution", "gain", "exposure", "fps"):
                if key in section:
                    kw[key] = section[key]
            cam = Camera(**kw)
            cam.open()
            return cam

        def build_sim() -> Any:
            from sciglob.camera import SimulatedCamera

            res = section.get("resolution", (640, 480)) if present else (640, 480)
            cam = SimulatedCamera(resolution=tuple(res))
            cam.open()
            return cam

        self.camera = self._try("camera", build_real, build_sim, present=present)

    def _open_imu(self) -> None:
        present = self.config.get("imu") is not None
        section: dict[str, Any] = self.config.get("imu") or {}

        def build_real() -> Any:
            from sciglob.imu import IMU

            serial = section.get("serial", {}) or {}
            imu = IMU(port=serial.get("port") or section.get("port"))
            imu.open()
            return imu

        def build_sim() -> Any:
            from sciglob.imu import IMU, SimulatedIMU

            imu = IMU(backend=SimulatedIMU())
            imu.open()
            return imu

        self.imu = self._try("imu", build_real, build_sim, present=present)

    # ------------------------------------------------------------------ #
    # Cross-device couplings
    # ------------------------------------------------------------------ #

    def _wire_couplings(self) -> None:
        """Wire relay/head-sensor spectrometer power-cycle marking.

        Before a head-sensor ``S1s``/``S2s`` relay (or a Samirob channel) drops
        USB power to a spectrometer, the attached ``Spectrometer`` must mark its
        native handle dead — otherwise a native call through a freed handle is an
        uncatchable access violation (the v0.0.8.7 crash class). We register a
        hook on the head sensor that calls ``mark_power_cycled`` on the matching
        spectrometer channel first.
        """
        if self.head_sensor is None or not self.spectrometers:
            return
        hook = getattr(self.head_sensor, "set_spec_power_cycle_hook", None)
        if not callable(hook):
            return

        specs = self.spectrometers

        def on_power_cycle(spec_number: int) -> None:
            idx = spec_number - 1
            if 0 <= idx < len(specs):
                dev = specs[idx]
                mark = getattr(dev, "mark_power_cycled", None)
                if callable(mark):
                    logger.info(
                        "Marking spectrometer %d power-cycled before relay fire",
                        spec_number,
                    )
                    mark()

        hook(on_power_cycle)

    def __repr__(self) -> str:
        opened = "open" if self._opened else "closed"
        n = len([s for s in self._status.values() if s.state != DeviceState.ABSENT])
        return f"<Instrument({opened}, {n} devices)>"

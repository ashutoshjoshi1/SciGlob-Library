"""Hardware-free simulated Avantes spectrometer.

:class:`SimulatedSpectrometer` mirrors the public surface of
:class:`~sciglob.spectrometers.avantes.AvantesSpectrometer` (``connect``,
``set_integration_time``, ``measure`` -> :class:`Spectrum`, ``wavelengths``,
``board_temperature`` / ``detector_temperature``, ``disconnect``, context
manager, ``mark_power_cycled``) but touches no DLL and no session. It generates
plausible spectra and supports optional random saturation (spec section 13).
"""

import logging
import math
import random
import threading
from typing import Any, Callable, Optional

from sciglob.spectrometers.avantes import MAX_CYCLES, Spectrum, make_counts

logger = logging.getLogger("sciglob.SimAvantes")


class SimulatedSpectrometer:
    """A drop-in simulation twin for :class:`AvantesSpectrometer`.

    Args:
        serial: Synthetic serial number.
        npixels: Pixel count of generated spectra.
        min_it_ms / max_it_ms / it_resolution_ms: integration-time limits + step.
        saturate_probability: Per-cycle chance of forcing a saturated pixel
            (spec section 13; default 0.0 = never).
        nbits: ADC bit depth for the saturation limit ``2**nbits - 1``.
        seed: Optional RNG seed for reproducible spectra.
        name: Logger/display name.
    """

    def __init__(
        self,
        serial: str = "SIM0001U1",
        npixels: int = 2048,
        *,
        min_it_ms: float = 2.4,
        max_it_ms: float = 4000.0,
        it_resolution_ms: Optional[float] = None,
        saturate_probability: float = 0.0,
        nbits: int = 16,
        seed: Optional[int] = None,
        name: str = "SimAvantes",
    ):
        self.name = name
        self.logger = logger
        self._serial = serial
        self._npixels = int(npixels)
        self._min_it_ms = float(min_it_ms)
        self._max_it_ms = float(max_it_ms)
        self._it_resolution_ms = it_resolution_ms
        self._saturate_probability = float(saturate_probability)
        self._sat_limit = float(2**nbits - 1)
        self._rng = random.Random(seed)
        self._lock = threading.RLock()

        self._spec_id: Optional[int] = None
        self._connected = False
        self._it_ms = self._min_it_ms
        self._wavelengths: Any = None

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
    def wavelengths(self) -> Any:
        return self._wavelengths

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> None:
        with self._lock:
            self._spec_id = self._rng.randint(1, 1_000_000)
            # Simple linear wavelength ramp (nm) for plausibility.
            self._wavelengths = make_counts([300.0 + i * 0.4 for i in range(self._npixels)])
            self._connected = True
            self.logger.info(
                "Simulated Avantes %s connected (handle=%s)", self._serial, self._spec_id
            )

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False
            self._spec_id = None

    def mark_power_cycled(self) -> None:
        with self._lock:
            self.logger.info("Simulated %s power-cycled; invalidating handle", self._serial)
            self._spec_id = None
            self._connected = False

    def __enter__(self) -> "SimulatedSpectrometer":
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    # -- configuration ------------------------------------------------------

    def set_integration_time(self, it_ms: float) -> None:
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("set_integration_time ignored: no active handle")
                return
            value = max(self._min_it_ms, min(self._max_it_ms, float(it_ms)))
            if self._it_resolution_ms:
                step = self._it_resolution_ms
                value = round(value / step) * step
                value = max(self._min_it_ms, min(self._max_it_ms, value))
            self._it_ms = value

    # -- acquisition --------------------------------------------------------

    @staticmethod
    def _check_ncycles(ncycles: int) -> int:
        """Mirror the real driver's uint16 cycle-count check (spec section 4.2)."""
        ncy = int(ncycles)
        if ncy < 1 or ncy > MAX_CYCLES:
            raise ValueError(
                f"ncycles={ncy} out of range: must be 1..{MAX_CYCLES} "
                f"(passed to the DLL as a uint16)."
            )
        return ncy

    def _generate_cycle(self) -> tuple[list[float], bool]:
        npix = self._npixels
        center = npix * 0.4
        width = max(1.0, npix * 0.15)
        peak = 0.45 * self._sat_limit
        base = 0.2 * self._sat_limit
        cycle: list[float] = []
        for i in range(npix):
            value = base + peak * math.exp(-((i - center) ** 2) / (2.0 * width * width))
            value += self._rng.uniform(-0.02, 0.02) * self._sat_limit
            if value < 0.0:
                value = 0.0
            cycle.append(value)
        saturated = False
        if self._saturate_probability and self._rng.random() < self._saturate_probability:
            cycle[self._rng.randrange(npix)] = self._sat_limit
            saturated = True
        if max(cycle) >= self._sat_limit:
            saturated = True
        return cycle, saturated

    def measure(
        self,
        ncycles: int = 1,
        *,
        store_to_ram: bool = False,
        abort_on_saturation: bool = True,
        timeout_s: Optional[float] = None,
        pump: Optional[Callable[[], None]] = None,
    ) -> Optional[Spectrum]:
        with self._lock:
            if self._spec_id is None:
                self.logger.warning("measure ignored: no active handle")
                return None
            npix = self._npixels
            accum = [0.0] * npix
            handled = 0
            sat_cycles = 0
            saturated = False
            timestamps: list[float] = []
            for cycle_index in range(int(ncycles)):
                if pump is not None:
                    try:
                        pump()
                    except Exception as exc:  # noqa: BLE001
                        self.logger.debug("pump callback raised: %s", exc)
                cycle, cycle_saturated = self._generate_cycle()
                timestamps.append((cycle_index + 1) * self._it_ms * 1e-3)
                if cycle_saturated:
                    saturated = True
                    sat_cycles += 1
                    if abort_on_saturation:
                        break
                for i in range(npix):
                    accum[i] += cycle[i]
                handled += 1
            denom = handled if handled else 1
            mean = [value / denom for value in accum]
            return Spectrum(
                counts=make_counts(mean),
                wavelengths=self._wavelengths,
                timestamps=timestamps,
                it_ms=self._it_ms,
                ncy_requested=int(ncycles),
                ncy_handled=handled,
                ncy_saturated=sat_cycles,
                saturated=saturated,
            )

    def start(
        self,
        ncycles: int = 1,
        *,
        store_to_ram: bool = False,
        abort_on_saturation: bool = True,
    ) -> None:
        with self._lock:
            self._pending = (int(ncycles), abort_on_saturation)

    def wait(
        self,
        timeout_s: Optional[float] = None,
        pump: Optional[Callable[[], None]] = None,
    ) -> Optional[Spectrum]:
        ncy, abort_on_saturation = getattr(self, "_pending", (1, True))
        return self.measure(ncy, abort_on_saturation=abort_on_saturation, pump=pump)

    def abort(self, ignore_errors: bool = True) -> None:
        # Nothing to stop in simulation.
        return None

    def read_data(self) -> Optional[tuple[Any, float]]:
        with self._lock:
            if self._spec_id is None:
                return None
            cycle, _ = self._generate_cycle()
            return make_counts(cycle), self._it_ms * 1e-3

    def read_aux_sensor(self, analogid: int) -> Optional[float]:
        with self._lock:
            if self._spec_id is None:
                return None
            return 1.0

    # -- auxiliary sensors --------------------------------------------------

    def board_temperature(self) -> float:
        with self._lock:
            if self._spec_id is None:
                return -99.0
            return round(25.0 + self._rng.uniform(-0.5, 0.5), 2)

    def detector_temperature(self) -> float:
        with self._lock:
            if self._spec_id is None:
                return -99.0
            return round(-5.0 + self._rng.uniform(-0.5, 0.5), 2)

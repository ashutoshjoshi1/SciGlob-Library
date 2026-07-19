"""Tests for the Avantes spectrometer package.

Every test runs against either the :class:`SimulatedSpectrometer` or an injected
fake DLL -- no real DLL, no hardware. The fake DLL below implements just enough
of the AvaSpec surface to exercise the session chokepoint, the connect/measure
poll path, and the Tier A / Tier B / wedge-cure recovery logic.
"""

import ctypes
import threading
import time

import pytest

from sciglob.core.exceptions import SessionRestartRequired
from sciglob.spectrometers import (
    AVS_INVALID_HANDLE,
    AVS_TIMEOUT_SENTINEL,
    ERROR_MESSAGES,
    AvaDeviceType,
    AvantesSpectrometer,
    AvaSession,
    AvsIdentityType,
    MeasConfigType,
    RecoveryPolicy,
    SimulatedSpectrometer,
    Spectrum,
    get_error_message,
)


def _deref(arg):
    """Unwrap a ctypes ``byref`` argument to its underlying object.

    ``byref(x)`` yields a CArgObject whose original object is available as
    ``._obj`` in CPython; plain objects pass through unchanged. This lets the
    Python fake DLL populate output parameters the same way the real DLL would.
    """
    return getattr(arg, "_obj", arg)


class FakeAvaDll:
    """Minimal in-memory stand-in for the AvaSpec DLL.

    Records every call name in :attr:`calls` and tracks the maximum number of
    threads simultaneously inside :meth:`AVS_Init` (to prove the session lock
    serializes calls).
    """

    def __init__(
        self,
        serial="1102185U1",
        npixels=8,
        activate_handle=42,
        activate_result=None,
        device_type=AvaDeviceType.TYPE_AS7010,
        raw_counts=1000.0,
    ):
        self.calls = []
        self.serial = serial
        self.npixels = npixels
        self.activate_handle = activate_handle
        self.activate_result = activate_result  # if set, AVS_Activate always returns it
        self.device_type = int(device_type)
        self.raw_counts = raw_counts
        self.reset_device_calls = 0
        self.done_calls = 0
        self.init_calls = 0
        # concurrency tracking for the RLock serialization test
        self._conc = 0
        self.max_concurrent = 0
        self._conc_lock = threading.Lock()

    # -- concurrency helpers ----------------------------------------------
    def _enter(self):
        with self._conc_lock:
            self._conc += 1
            self.max_concurrent = max(self.max_concurrent, self._conc)

    def _leave(self):
        with self._conc_lock:
            self._conc -= 1

    def _record(self, name):
        self.calls.append(name)

    # -- lifecycle ---------------------------------------------------------
    def AVS_Init(self, mode):
        self._record("AVS_Init")
        self.init_calls += 1
        self._enter()
        time.sleep(0.003)  # widen the window so a missing lock would overlap
        self._leave()
        return 1  # one USB device

    def AVS_Done(self):
        self._record("AVS_Done")
        self.done_calls += 1
        return 0

    def AVS_UpdateUSBDevices(self):
        self._record("AVS_UpdateUSBDevices")
        return 1

    def AVS_GetList(self, size, required_ref, data_ref):
        self._record("AVS_GetList")
        data = _deref(data_ref)
        required = _deref(required_ref)
        data[0].SerialNumber = self.serial.encode("utf-8")
        data[0].UserFriendlyName = b"FakeAvaSpec"
        data[0].Status = b"\x01"
        if hasattr(required, "value"):
            required.value = ctypes.sizeof(AvsIdentityType)
        return 1  # one identity returned

    def AVS_Activate(self, identity_ref):
        self._record("AVS_Activate")
        if self.activate_result is not None:
            return self.activate_result
        return self.activate_handle

    def AVS_Deactivate(self, handle):
        self._record("AVS_Deactivate")
        return 1

    # -- config / info -----------------------------------------------------
    def AVS_GetNumPixels(self, handle, ref):
        self._record("AVS_GetNumPixels")
        _deref(ref).value = self.npixels
        return 0

    def AVS_GetDeviceType(self, handle, ref):
        self._record("AVS_GetDeviceType")
        _deref(ref).value = self.device_type
        return 0

    def AVS_PrepareMeasure(self, handle, cfg_ref):
        self._record("AVS_PrepareMeasure")
        return 0

    def AVS_GetLambda(self, handle, ref):
        self._record("AVS_GetLambda")
        buf = _deref(ref)
        for i in range(self.npixels):
            buf[i] = 300.0 + i * 0.5
        return 0

    # -- acquisition -------------------------------------------------------
    def AVS_Measure(self, handle, hwnd, ncy):
        self._record("AVS_Measure")
        return 0

    def AVS_PollScan(self, handle):
        self._record("AVS_PollScan")
        return 1  # data always available immediately

    def AVS_GetScopeData(self, handle, time_label_ref, buf_ref):
        self._record("AVS_GetScopeData")
        _deref(time_label_ref).value = 123456
        buf = _deref(buf_ref)
        for i in range(self.npixels):
            buf[i] = self.raw_counts + i
        return 0

    def AVS_StopMeasure(self, handle):
        self._record("AVS_StopMeasure")
        return 0

    # -- aux / recovery ----------------------------------------------------
    def AVS_GetAnalogIn(self, handle, analog_id, ref):
        self._record("AVS_GetAnalogIn")
        _deref(ref).value = 1.0
        return 0

    def AVS_ResetDevice(self, handle):
        self._record("AVS_ResetDevice")
        self.reset_device_calls += 1
        return 0


def _noop_sleep(_seconds):
    """Injected sleep: never actually waits (keeps recovery tests fast)."""
    return None


def _fast_policy(**overrides):
    """A RecoveryPolicy with tiny budgets so recovery tests never wall-clock wait."""
    defaults = {
        "reenum_poll_s": 0.0,
        "budget_s": 0.5,
        "first_connect_budget_s": 0.5,
        "settle_s": 0.0,
        "activate_gap_s": 0.0,
        "post_activate_settle_s": 0.0,
        "pre_activate_settle_s": 0.0,
        "it_handshake_settle_s": 0.0,
        "stop_measure_settle_s": 0.0,
        "reset_settle_s": 0.0,
        "poll_slice_s": 0.0,
    }
    defaults.update(overrides)
    return RecoveryPolicy(**defaults)


def _make_spectrometer(fake, **kwargs):
    session = AvaSession(dll=fake, sleep=_noop_sleep)
    params = {
        "serial": fake.serial,
        "session": session,
        "npixels": fake.npixels,
        "device_type": AvaDeviceType(fake.device_type),
        "recovery_policy": _fast_policy(),
        "sleep": _noop_sleep,
    }
    params.update(kwargs)
    spec = AvantesSpectrometer(**params)
    return spec, session


# ---------------------------------------------------------------------------
# Error table
# ---------------------------------------------------------------------------


def test_error_table_lookups():
    """The complete error table resolves to the verbatim spec messages."""
    assert get_error_message(0) == "OK"
    assert get_error_message(-1) == "Function called with invalid parameter value."
    assert get_error_message(-4) == "AvsHandle is unknown in the DLL."
    assert (
        get_error_message(-11)
        == "Measurement preparation failed because integration time is invalid (for selected sensor)."
    )
    assert get_error_message(-22) == "Reply is not a recognized protocol message"
    assert get_error_message(-144) == "Factor should be in range 0.0 -4.0"
    assert get_error_message(-999) == "Spectrometer operation timed out."
    assert get_error_message(1000) == "Invalid Handle."
    # Reserved slots present; -23 absent.
    assert get_error_message(-7) == "Reserved (-7)"
    assert get_error_message(-13) == "Reserved (-13)"
    assert -23 not in ERROR_MESSAGES
    # Unknown codes never raise.
    assert "unknown error code (777)" == get_error_message(777)
    # Sentinels.
    assert AVS_INVALID_HANDLE == 1000
    assert AVS_TIMEOUT_SENTINEL == -999


def test_structures_are_byte_exact():
    """ctypes structures match the authoritative byte layout (spec section 2)."""
    assert ctypes.sizeof(AvsIdentityType) == 75
    assert ctypes.sizeof(MeasConfigType) == 41
    assert MeasConfigType._pack_ == 1
    assert AvsIdentityType._pack_ == 1


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


def test_simulator_measure_returns_spectrum_of_right_length():
    """SimulatedSpectrometer.measure returns a Spectrum sized to the pixel count."""
    sim = SimulatedSpectrometer(npixels=256, seed=1)
    sim.connect()
    spectrum = sim.measure(3)
    assert isinstance(spectrum, Spectrum)
    assert len(spectrum) == 256
    assert len(spectrum.counts) == 256
    assert len(spectrum.wavelengths) == 256
    assert spectrum.ncy_requested == 3
    assert spectrum.ncy_handled == 3
    assert not spectrum.saturated
    sim.disconnect()


def test_simulator_public_surface_and_context_manager():
    """The simulator exposes the same surface as the real driver."""
    with SimulatedSpectrometer(npixels=64, seed=7) as sim:
        assert sim.is_connected
        sim.set_integration_time(100.0)
        assert sim.integration_time_ms == 100.0
        assert isinstance(sim.board_temperature(), float)
        assert isinstance(sim.detector_temperature(), float)
        assert len(sim.wavelengths) == 64
    # After the context manager the device is disconnected.
    assert not sim.is_connected
    assert sim.board_temperature() == -99.0


def test_simulator_random_saturation():
    """With saturate_probability=1 every cycle saturates and is flagged."""
    sim = SimulatedSpectrometer(npixels=32, saturate_probability=1.0, seed=3)
    sim.connect()
    spectrum = sim.measure(2, abort_on_saturation=True)
    assert spectrum.saturated
    assert spectrum.ncy_saturated >= 1
    assert len(spectrum) == 32


def test_simulator_mark_power_cycled():
    """mark_power_cycled invalidates the handle; measure then no-ops."""
    sim = SimulatedSpectrometer(npixels=16, seed=5)
    sim.connect()
    assert sim.measure(1) is not None
    sim.mark_power_cycled()
    assert not sim.is_connected
    assert sim.measure(1) is None


# ---------------------------------------------------------------------------
# Dead-handle guards
# ---------------------------------------------------------------------------


def test_avantes_dead_handle_guards():
    """Every guarded method is safe when the handle is None (fresh and post-power-cycle)."""
    fake = FakeAvaDll(npixels=8)

    # (a) Fresh, never-connected spectrometer: spec_id is None.
    spec, _session = _make_spectrometer(fake)
    assert spec._spec_id is None
    # None of these should raise or touch the DLL.
    spec.set_integration_time(500.0)
    assert spec.measure(1) is None
    assert spec.read_data() is None
    assert spec.read_aux_sensor(0) is None
    spec.abort()
    assert spec.board_temperature() == -99.0
    assert spec.detector_temperature() == -99.0
    assert spec.wavelengths is None
    assert fake.calls == []  # guards fired before any DLL call

    # (b) Connect, then power-cycle, then re-check the guards.
    spec.connect()
    assert spec.is_connected
    spec.mark_power_cycled()
    assert spec._spec_id is None
    calls_after_mark = len(fake.calls)
    spec.set_integration_time(500.0)
    assert spec.measure(1) is None
    assert spec.read_data() is None
    assert spec.read_aux_sensor(6) is None
    spec.abort()
    assert spec.board_temperature() == -99.0
    # No further DLL calls were made once the handle was cleared.
    assert len(fake.calls) == calls_after_mark


def test_avantes_measure_over_fake_dll():
    """A full connect + measure over the fake DLL yields a right-sized Spectrum."""
    fake = FakeAvaDll(npixels=8, raw_counts=1000.0)
    spec, _session = _make_spectrometer(fake)
    spec.connect()
    spectrum = spec.measure(2)
    assert isinstance(spectrum, Spectrum)
    assert len(spectrum) == 8
    # discriminator_factor default 4.0 applied to raw counts.
    assert spectrum.counts[0] == pytest.approx(1000.0 * 4.0)
    assert spectrum.ncy_handled == 2
    assert len(spectrum.wavelengths) == 8
    spec.disconnect()
    assert "AVS_Done" not in fake.calls  # disconnect never calls Done
    assert "AVS_Deactivate" in fake.calls


# ---------------------------------------------------------------------------
# Tier A / Tier B recovery
# ---------------------------------------------------------------------------


def test_tier_a_never_calls_done():
    """Tier A recovery re-activates via a fresh identity, never Done/Init."""
    fake = FakeAvaDll(npixels=8)
    spec, _session = _make_spectrometer(fake)
    spec.connect()
    # Drop the connect-time calls so we only inspect what Tier A does.
    fake.calls.clear()

    recovered = spec._tier_a_recover()

    assert recovered is True
    assert "AVS_Init" not in fake.calls
    assert "AVS_Done" not in fake.calls
    assert "AVS_Deactivate" in fake.calls
    assert "AVS_Activate" in fake.calls
    # Sanity: no accidental Init/Done at the session level either.
    assert fake.done_calls == 0


def test_tier_b_sentinel_escalation():
    """Persistent AVS_Activate==1000 escalates to SessionRestartRequired (Tier B)."""
    fake = FakeAvaDll(npixels=8, activate_result=AVS_INVALID_HANDLE)
    spec, _session = _make_spectrometer(fake)
    # Not connected: Tier A deactivates (no-op), re-enumerates (found), then
    # exhausts activate attempts, all returning 1000 -> Tier B.
    with pytest.raises(SessionRestartRequired):
        spec._tier_a_recover()
    # Exactly activate_attempts activate calls were made.
    assert fake.calls.count("AVS_Activate") == spec.policy.activate_attempts
    assert "AVS_Done" not in fake.calls
    assert "AVS_Init" not in fake.calls


def test_rapid_refail_gated_on_no_data():
    """Wedge-cure reboot fires only when no data has arrived since the last recovery."""
    fake = FakeAvaDll(npixels=8, device_type=AvaDeviceType.TYPE_AS7010)
    spec, _session = _make_spectrometer(fake)
    spec.connect()

    # Data has just arrived -> wedge cure is gated (no reboot).
    spec.measure(1)
    assert spec._data_since_last_recovery is True
    assert spec._wedge_cure() is False
    assert fake.reset_device_calls == 0

    # A Tier A recovery resets the "data since recovery" flag; with no data
    # arriving afterwards the wedge cure now reboots the device.
    assert spec._tier_a_recover() is True
    assert spec._data_since_last_recovery is False
    assert spec._wedge_cure() is True
    assert fake.reset_device_calls == 1


def test_wedge_cure_unsupported_devtype_skips():
    """AVS_ResetDevice is skipped on AS5216 (unsupported family)."""
    fake = FakeAvaDll(npixels=8, device_type=AvaDeviceType.TYPE_AS5216)
    spec, _session = _make_spectrometer(fake)
    spec.connect()
    spec._data_since_last_recovery = False
    assert spec._wedge_cure() is False
    assert fake.reset_device_calls == 0


# ---------------------------------------------------------------------------
# Session chokepoint
# ---------------------------------------------------------------------------


def test_session_rlock_serializes_avs_calls():
    """The session RLock serializes _avs: never more than one call in flight."""
    fake = FakeAvaDll()
    session = AvaSession(dll=fake, sleep=_noop_sleep)

    def worker():
        session._avs("AVS_Init", 0)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert fake.init_calls == 12
    assert fake.max_concurrent == 1  # lock kept them strictly serialized


def test_session_init_idempotent_and_enumerate():
    """init() is idempotent and enumerate() decodes identities."""
    fake = FakeAvaDll(serial="2106511U1")
    session = AvaSession(dll=fake, sleep=_noop_sleep)
    assert session.init() == 1
    assert session.init() == 1  # idempotent: no second AVS_Init
    assert fake.init_calls == 1
    identities = session.enumerate()
    assert len(identities) == 1
    assert identities[0].serial == "2106511U1"


def test_session_done_watchdog_survives_hang():
    """done() returns even if AVS_Done hangs (external watchdog)."""

    class HangingDll(FakeAvaDll):
        def AVS_Done(self):
            self._record("AVS_Done")
            time.sleep(5.0)  # simulate the known DLL hang
            return 0

    fake = HangingDll()
    session = AvaSession(dll=fake, sleep=_noop_sleep)
    session.init()
    start = time.monotonic()
    session.done(timeout_s=0.2)  # must not block for the full 5 s
    elapsed = time.monotonic() - start
    assert elapsed < 2.0
    assert session.is_initialized is False


def test_dll_version_parsed_from_path():
    """dll_version() reports the version parsed from the DLL path; mismatch warns only."""
    session = AvaSession(dll_path=r"C:/x/Avaspec-DLL_9.13.0.0_64bits/avaspecx64.dll")
    assert session.dll_version() == "9.13.0.0"

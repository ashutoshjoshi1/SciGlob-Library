"""Tests for the xIMU3 head IMU (sciglob.imu), driven by the simulated backend."""

import pytest

from sciglob.core.exceptions import ImuError
from sciglob.imu import (
    IMU,
    EULER_STALE_S,
    MESSAGE_TYPES,
    QuaternionMessage,
    SimulatedIMU,
)


@pytest.fixture
def sim_imu():
    """An opened IMU over a SimulatedIMU backend."""
    backend = SimulatedIMU()
    imu = IMU(backend=backend)
    imu.open()
    yield imu, backend
    imu.close()


class TestSimulatedIMU:
    """IMU behaviour driven through the simulated (hardware-free) backend."""

    def test_open_registers_callbacks_and_sets_open(self, sim_imu):
        imu, backend = sim_imu
        assert imu.is_open is True
        assert backend.is_open is True
        # All four streams were registered on the backend.
        for mt in MESSAGE_TYPES:
            assert mt in backend._callbacks

    def test_readings_none_before_any_message(self):
        backend = SimulatedIMU()
        imu = IMU(backend=backend)
        imu.open()
        readings = imu.get_readings()
        assert readings == {
            "Roll": None,
            "Pitch": None,
            "Yaw": None,
            "Temp": None,
            "Battery": None,
        }
        imu.close()

    def test_euler_updates_latest_values(self, sim_imu):
        imu, backend = sim_imu
        backend.push_euler(10.0, 5.0, 45.0)
        readings = imu.get_readings()
        assert readings["Roll"] == 10.0
        assert readings["Pitch"] == 5.0
        assert readings["Yaw"] == 45.0

    def test_temperature_and_battery_updates(self, sim_imu):
        imu, backend = sim_imu
        backend.push_temperature(31.5)
        backend.push_battery(87.0, voltage=3.9)
        readings = imu.get_readings()
        assert readings["Temp"] == 31.5
        assert readings["Battery"] == 87.0

    def test_to_zenith_azimuth_mapping(self, sim_imu):
        # spec §6: roll->zenith, yaw->azimuth.
        imu, backend = sim_imu
        backend.push_euler(12.0, 0.0, 200.0)
        zenith, azimuth = imu.to_zenith_azimuth()
        assert zenith == 12.0
        assert azimuth == 200.0

    def test_to_zenith_azimuth_none_before_reading(self, sim_imu):
        imu, _ = sim_imu
        assert imu.to_zenith_azimuth() == (None, None)

    def test_zenith_sign_configurable(self):
        # spec §6.2: zenith sign is a rig-wiring convention, must be configurable.
        backend = SimulatedIMU()
        imu = IMU(backend=backend, zenith_sign=-1)
        imu.open()
        backend.push_euler(30.0, 0.0, 90.0)
        zenith, azimuth = imu.to_zenith_azimuth()
        assert zenith == -30.0
        assert azimuth == 90.0
        imu.close()

    def test_is_streaming_true_after_orientation(self, sim_imu):
        imu, backend = sim_imu
        assert imu.is_streaming is False  # nothing yet
        backend.push_euler(1.0, 2.0, 3.0)
        assert imu.is_streaming is True

    def test_is_streaming_false_when_only_non_orientation(self, sim_imu):
        imu, backend = sim_imu
        backend.push_temperature(25.0)
        backend.push_battery(50.0)
        # Temperature/battery are not orientation streams.
        assert imu.is_streaming is False

    def test_is_streaming_goes_stale(self):
        backend = SimulatedIMU()
        imu = IMU(backend=backend, streaming_window_s=0.0)
        imu.open()
        backend.push_euler(1.0, 2.0, 3.0)
        # A zero-length window means any elapsed time reads as not-streaming.
        assert imu.is_streaming is False
        imu.close()

    def test_context_manager_opens_and_closes(self):
        backend = SimulatedIMU()
        with IMU(backend=backend) as imu:
            assert imu.is_open is True
            assert backend.is_open is True
        assert imu.is_open is False
        assert backend.is_open is False

    def test_open_idempotent(self, sim_imu):
        imu, _ = sim_imu
        imu.open()  # second call is a no-op
        assert imu.is_open is True

    def test_close_idempotent(self):
        backend = SimulatedIMU()
        imu = IMU(backend=backend)
        imu.open()
        imu.close()
        imu.close()  # must not raise
        assert imu.is_open is False


class TestQuaternionFallback:
    """Quaternion->Euler fallback semantics (spec §5)."""

    def test_quaternion_used_when_no_euler(self, sim_imu):
        imu, backend = sim_imu
        # Identity quaternion -> roll=pitch=yaw=0.
        backend.push_quaternion(1.0, 0.0, 0.0, 0.0)
        readings = imu.get_readings()
        assert readings["Roll"] == pytest.approx(0.0)
        assert readings["Pitch"] == pytest.approx(0.0)
        assert readings["Yaw"] == pytest.approx(0.0)

    def test_quaternion_conversion_yaw(self, sim_imu):
        imu, backend = sim_imu
        # 90 deg rotation about Z: w=cos(45), z=sin(45) -> yaw ~= 90.
        import math

        h = math.sqrt(2) / 2
        backend.push_quaternion(h, 0.0, 0.0, h)
        readings = imu.get_readings()
        assert readings["Yaw"] == pytest.approx(90.0, abs=1e-6)

    def test_fresh_euler_suppresses_quaternion(self, sim_imu):
        # spec §5: device Euler is preferred; a quaternion arriving while Euler
        # is fresh must not overwrite the stored orientation.
        imu, backend = sim_imu
        backend.push_euler(15.0, 0.0, 30.0)
        backend.push_quaternion(1.0, 0.0, 0.0, 0.0)  # would give 0,0,0 if used
        readings = imu.get_readings()
        assert readings["Roll"] == 15.0
        assert readings["Yaw"] == 30.0
        # But the quaternion was still counted.
        assert imu.message_counts()["quaternion"] == 1

    def test_stale_euler_allows_quaternion_fallback(self):
        # Simulate a stale Euler timestamp by directly aging the marker.
        backend = SimulatedIMU()
        imu = IMU(backend=backend)
        imu.open()
        backend.push_euler(15.0, 0.0, 30.0)
        import time

        # Force the Euler marker older than the staleness window.
        with imu._lock:
            imu._last_euler_monotonic = time.monotonic() - (EULER_STALE_S + 1.0)
        backend.push_quaternion(1.0, 0.0, 0.0, 0.0)
        readings = imu.get_readings()
        assert readings["Roll"] == pytest.approx(0.0)
        assert readings["Yaw"] == pytest.approx(0.0)
        imu.close()


class TestBackendSelection:
    """Backend defaulting and the missing-extra error path."""

    def test_real_backend_missing_ximu3_raises(self, monkeypatch):
        # When ximu3 is absent and no backend is supplied, the real backend is
        # requested and must raise ImuError naming the extra to install.
        import sciglob.imu as imu_mod

        monkeypatch.setattr(imu_mod, "ximu3", None)
        with pytest.raises(ImuError) as excinfo:
            IMU()
        assert "sciglob[imu]" in str(excinfo.value)

    def test_real_backend_direct_missing_ximu3_raises(self, monkeypatch):
        import sciglob.imu as imu_mod

        monkeypatch.setattr(imu_mod, "ximu3", None)
        with pytest.raises(ImuError):
            imu_mod.RealImuBackend(port="COM3")


class TestQuaternionMessage:
    """The simulated QuaternionMessage conversion helper."""

    def test_identity_quaternion_is_zero_euler(self):
        euler = QuaternionMessage(0, 1.0, 0.0, 0.0, 0.0).to_euler_angles_message()
        assert euler.roll == pytest.approx(0.0)
        assert euler.pitch == pytest.approx(0.0)
        assert euler.yaw == pytest.approx(0.0)


def test_imu_counts_messages_per_type():
    """Silent-stream diagnostic (spec §4): message_counts() reflects exactly
    the number of messages pushed per type.

    Push N euler, M quaternion, K temperature messages via the simulated
    backend and assert the per-type counters equal N / M / K.
    """
    n_euler = 7
    m_quat = 4
    k_temp = 3

    backend = SimulatedIMU()
    imu = IMU(backend=backend)
    imu.open()

    for _ in range(n_euler):
        backend.push_euler(1.0, 2.0, 3.0)
    for _ in range(m_quat):
        backend.push_quaternion(1.0, 0.0, 0.0, 0.0)
    for _ in range(k_temp):
        backend.push_temperature(25.0)

    counts = imu.message_counts()
    assert counts["euler"] == n_euler
    assert counts["quaternion"] == m_quat
    assert counts["temperature"] == k_temp
    assert counts["battery"] == 0  # never pushed

    imu.close()

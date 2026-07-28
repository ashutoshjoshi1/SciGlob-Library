"""Tests for sciglob.camera (OpenCV probe via injected fakes + simulated)."""

from typing import Any, List, Optional, Tuple

import pytest

from sciglob.camera import (
    Camera,
    CameraError,
    Frame,
    OpenCVCamera,
    SimpleFrame,
    SimulatedCamera,
    to_grayscale,
)


# ---------------------------------------------------------------------------
# Fake VideoCapture objects for driving the OpenCV probe without cv2.
# ---------------------------------------------------------------------------
class FakeCapture:
    """Minimal stand-in for cv2.VideoCapture used by the injected factory."""

    def __init__(
        self,
        opened: bool = True,
        frame: Any = None,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> None:
        self._opened = opened
        self._frame = frame
        # Effective resolution reported by get(); defaults to frame shape.
        if resolution is not None:
            self._w, self._h = resolution
        elif frame is not None:
            wh = _shape_wh(frame)
            self._w, self._h = wh if wh else (0, 0)
        else:
            self._w = self._h = 0
        self.released = False
        self.props: dict = {}
        self.read_count = 0

    def isOpened(self) -> bool:
        return self._opened

    def read(self) -> Tuple[bool, Any]:
        self.read_count += 1
        if self._frame is None:
            return False, None
        return True, self._frame

    def set(self, prop: int, value: float) -> bool:
        self.props[prop] = value
        return True

    def get(self, prop: int) -> float:
        # 3 = width, 4 = height (OpenCV property IDs)
        if prop == 3:
            return float(self._w)
        if prop == 4:
            return float(self._h)
        return float(self.props.get(prop, 0.0))

    def release(self) -> None:
        self.released = True


def _shape_wh(frame: Any) -> Optional[Tuple[int, int]]:
    shape = getattr(frame, "shape", None)
    if shape is not None and len(shape) >= 2:
        return int(shape[1]), int(shape[0])
    return None


def make_factory(captures: List[FakeCapture]):
    """Return a capture_factory yielding the given captures by index."""

    def factory(index: int) -> FakeCapture:
        return captures[index]

    return factory


# ---------------------------------------------------------------------------
# The mandated regression test.
# ---------------------------------------------------------------------------
def test_camera_accepts_first_working_frame_any_resolution():
    # Index 0 opens but read() returns (False, None); index 1 yields a frame
    # at a resolution DIFFERENT from the hint. Camera must select index 1 and
    # store the EFFECTIVE resolution, not the hint.
    hint = (640, 480)
    effective = (1280, 720)
    good_frame = SimpleFrame(effective[0], effective[1], fill=5)

    cap0 = FakeCapture(opened=True, frame=None)  # opens, no frame
    cap1 = FakeCapture(opened=True, frame=good_frame, resolution=effective)
    # extra indices 2..4 also fail to open (probe range is 0..4)
    caps = [cap0, cap1] + [FakeCapture(opened=False) for _ in range(3)]

    cam = Camera(
        backend="opencv",
        resolution=hint,
        capture_factory=make_factory(caps),
    )
    cam.open()

    assert cam.selected_index == 1
    assert cam.effective_resolution == effective
    assert cam.effective_resolution != hint
    # index 0 was rejected and released
    assert cap0.released is True
    cam.release()
    assert cap1.released is True


# ---------------------------------------------------------------------------
# OpenCV backend probe behaviour.
# ---------------------------------------------------------------------------
def test_opencv_probe_raises_when_no_camera_delivers_frame():
    caps = [FakeCapture(opened=False) for _ in range(5)]
    cam = Camera(backend="opencv", capture_factory=make_factory(caps))
    with pytest.raises(CameraError):
        cam.open()


def test_opencv_probe_accepts_first_of_multiple_working():
    f2 = SimpleFrame(320, 240, fill=1)
    f3 = SimpleFrame(800, 600, fill=1)
    caps = [
        FakeCapture(opened=False),
        FakeCapture(opened=True, frame=None),
        FakeCapture(opened=True, frame=f2, resolution=(320, 240)),
        FakeCapture(opened=True, frame=f3, resolution=(800, 600)),
        FakeCapture(opened=False),
    ]
    cam = Camera(backend="opencv", capture_factory=make_factory(caps))
    cam.open()
    assert cam.selected_index == 2
    assert cam.effective_resolution == (320, 240)


def test_opencv_specific_index_only_probes_that_index():
    frame = SimpleFrame(100, 100, fill=1)
    caps = [
        FakeCapture(opened=True, frame=SimpleFrame(10, 10)),  # index 0, ignored
        FakeCapture(opened=True, frame=SimpleFrame(20, 20)),
        FakeCapture(opened=True, frame=frame, resolution=(100, 100)),
        FakeCapture(opened=False),
        FakeCapture(opened=False),
    ]
    cam = Camera(backend="opencv", index=2, capture_factory=make_factory(caps))
    cam.open()
    assert cam.selected_index == 2
    assert cam.effective_resolution == (100, 100)


def test_opencv_resolution_hint_requested_via_set():
    frame = SimpleFrame(1024, 768, fill=1)
    cap = FakeCapture(opened=True, frame=frame, resolution=(1024, 768))
    cam = Camera(
        backend="opencv",
        index=0,
        resolution=(640, 480),
        capture_factory=make_factory([cap]),
    )
    cam.open()
    # The hint was requested via set() even though the device ignored it.
    assert cap.props[3] == 640  # CAP_PROP_FRAME_WIDTH
    assert cap.props[4] == 480  # CAP_PROP_FRAME_HEIGHT
    # But the stored resolution is the effective one.
    assert cam.effective_resolution == (1024, 768)


def test_opencv_capture_uses_double_read():
    frame = SimpleFrame(64, 48, fill=7)
    cap = FakeCapture(opened=True, frame=frame, resolution=(64, 48))
    cam = Camera(backend="opencv", index=0, capture_factory=make_factory([cap]))
    cam.open()
    reads_after_probe = cap.read_count
    f = cam.capture()
    assert isinstance(f, Frame)
    assert f.image is frame
    # One warm-up read + one real read == 2 additional reads.
    assert cap.read_count - reads_after_probe == 2


def test_opencv_capture_before_open_raises():
    cap = FakeCapture(opened=True, frame=SimpleFrame(10, 10))
    cam = Camera(backend="opencv", index=0, capture_factory=make_factory([cap]))
    with pytest.raises(CameraError):
        cam.capture()


def test_opencv_capture_raises_when_read_fails_after_open():
    class FlakyCapture(FakeCapture):
        def read(self) -> Tuple[bool, Any]:
            self.read_count += 1
            # First read (probe) succeeds; later reads fail.
            if self.read_count == 1:
                return True, self._frame
            return False, None

    cap = FlakyCapture(opened=True, frame=SimpleFrame(10, 10), resolution=(10, 10))
    cam = Camera(backend="opencv", index=0, capture_factory=make_factory([cap]))
    cam.open()
    with pytest.raises(CameraError):
        cam.capture()


def test_opencv_missing_cv2_without_factory_raises_install_hint():
    import sciglob.camera as camera_mod

    # Only meaningful when cv2 is genuinely absent in this environment.
    if camera_mod.cv2 is not None:
        pytest.skip("cv2 is installed; install-hint path not exercised")
    cam = Camera(backend="opencv", index=0)  # no factory -> needs cv2
    with pytest.raises(CameraError) as excinfo:
        cam.open()
    assert "pip install sciglob[camera]" in str(excinfo.value)


def test_release_is_idempotent_and_exception_proof():
    cap = FakeCapture(opened=True, frame=SimpleFrame(10, 10), resolution=(10, 10))
    cam = Camera(backend="opencv", index=0, capture_factory=make_factory([cap]))
    cam.open()
    cam.release()
    cam.release()  # second call must not raise
    assert cap.released is True


def test_opencv_context_manager_opens_and_releases():
    cap = FakeCapture(opened=True, frame=SimpleFrame(10, 10), resolution=(10, 10))
    factory = make_factory([cap])
    with Camera(backend="opencv", index=0, capture_factory=factory) as cam:
        assert cam.is_open() is True
    assert cap.released is True


def test_directx_alias_selects_opencv_backend():
    cap = FakeCapture(opened=True, frame=SimpleFrame(10, 10), resolution=(10, 10))
    cam = Camera(backend="directx", index=0, capture_factory=make_factory([cap]))
    assert cam.backend == "directx"
    cam.open()
    assert cam.selected_index == 0


def test_unknown_backend_raises():
    with pytest.raises(CameraError):
        Camera(backend="nonsense")


# ---------------------------------------------------------------------------
# Simulated backend.
# ---------------------------------------------------------------------------
def test_simulated_camera_reports_requested_resolution():
    cam = SimulatedCamera(resolution=(320, 240))
    cam.open()
    assert cam.effective_resolution == (320, 240)
    frame = cam.capture()
    assert isinstance(frame, Frame)
    assert frame.image.shape == (240, 320)  # (height, width)
    cam.release()


def test_simulated_camera_generates_sun_spot():
    cam = SimulatedCamera(resolution=(100, 100), spot_radius=10, spot_value=200)
    cam.open()
    frame = cam.capture()
    cx, cy = cam.last_true_center
    # Center pixel should be lit; a far corner should be background.
    img = frame.image
    if isinstance(img, SimpleFrame):  # SimpleFrame stand-in
        assert img.data[int(cy)][int(cx)] == 200
        assert img.data[0][0] == 0
    else:  # numpy path
        assert img[int(cy), int(cx)] == 200
        assert img[0, 0] == 0


def test_simulated_camera_frame_index_is_monotonic():
    cam = SimulatedCamera(resolution=(32, 32))
    cam.open()
    indices = [cam.capture().index for _ in range(3)]
    assert indices == [0, 1, 2]


def test_simulated_camera_cycles_canned_frames():
    frames = [SimpleFrame(8, 8, fill=1), SimpleFrame(8, 8, fill=2)]
    cam = SimulatedCamera(resolution=(8, 8), frames=frames)
    cam.open()
    got = [cam.capture().image for _ in range(4)]
    assert got[0] is frames[0]
    assert got[1] is frames[1]
    assert got[2] is frames[0]  # round-robin
    assert got[3] is frames[1]


def test_simulated_capture_before_open_raises():
    cam = SimulatedCamera(resolution=(16, 16))
    with pytest.raises(CameraError):
        cam.capture()


def test_simulated_capture_gray_returns_grayscale_frame():
    cam = SimulatedCamera(resolution=(16, 16))
    cam.open()
    gray = cam.capture_gray()
    assert isinstance(gray, Frame)
    # Simulated frames are already single-channel (2D shape).
    assert len(gray.image.shape) == 2


def test_simulated_camera_via_frontend_backend_name():
    cam = Camera(backend="simulated", resolution=(48, 48))
    assert cam.backend == "simulated"
    cam.open()
    assert cam.effective_resolution == (48, 48)


def test_opencv_camera_convenience_class():
    cap = FakeCapture(opened=True, frame=SimpleFrame(64, 64), resolution=(64, 64))
    cam = OpenCVCamera(index=0, capture_factory=make_factory([cap]))
    assert cam.backend == "opencv"
    cam.open()
    assert cam.effective_resolution == (64, 64)


# ---------------------------------------------------------------------------
# Grayscale helper.
# ---------------------------------------------------------------------------
def test_to_grayscale_passthrough_for_2d_standin():
    frame = SimpleFrame(8, 8, fill=3)
    assert to_grayscale(frame) is frame

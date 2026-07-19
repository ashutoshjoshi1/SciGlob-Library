"""Camera driver for SciGlob (OpenCV real backend + Simulated backend).

This module ports the field-proven camera behaviour of the legacy BlickO
``blick_camerecha.py`` class and the modern Pandora2.0 ``OpenCvCamera`` port
into a single, dependency-optional interface.

Design notes (spec references are to ``specs/camera.md``):

* Two backends live behind one :class:`Camera` frontend: ``"opencv"`` (real,
  needs OpenCV) and ``"simulated"`` (pure Python, zero extras). ``"directx"``
  is accepted as a compatibility alias that selects OpenCV with the
  ``CAP_DSHOW`` DirectShow preference (spec §12 / §1 ``valcamrm``).
* ``cv2`` is imported lazily-guarded (``try/except -> None``). The clear
  ``CameraError`` telling the user to ``pip install sciglob[camera]`` is only
  raised when the OpenCV backend is *actually requested* and no capture-factory
  was injected -- so tests can exercise the probe logic without OpenCV present.
* OpenCV probe rules (spec §3.3, the decided rewrite behaviour that supersedes
  legacy exact-match rejection): probe indices 0-4; ACCEPT THE FIRST device
  that actually delivers a frame; request the configured resolution only as a
  hint (never reject on mismatch); then store the *effective* resolution read
  back from the device. ``gain``/``exposure``/``fps`` are optional and skipped
  silently when unconfigured. A double-read is used to skip the stale warm-up
  frame (spec §4). ``release()`` is explicit and exception-proof (spec §9.3).
* ``numpy`` is also optional: when present, simulated frames are real ndarrays;
  when absent, a minimal :class:`SimpleFrame` stand-in is produced instead.
"""

from __future__ import annotations

import logging
import platform
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple, cast

from sciglob.core.exceptions import CameraError

# ---------------------------------------------------------------------------
# Optional vendor dependencies -- guarded so the module imports everywhere.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - trivial import guard
    import cv2 as _cv2

    cv2: Any = _cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:  # pragma: no cover - trivial import guard
    import numpy as _np

    np: Any = _np
except ImportError:  # pragma: no cover
    np = None


# ---------------------------------------------------------------------------
# OpenCV VideoCapture property IDs (spec §5). Hard-coded to the well-known
# integer values so the probe/settings code works even when cv2 is absent
# (real cv2.VideoCapture accepts the same integers).
# ---------------------------------------------------------------------------
_PROP_FRAME_WIDTH = 3
_PROP_FRAME_HEIGHT = 4
_PROP_FPS = 5
_PROP_GAIN = 14
_PROP_EXPOSURE = 15

# After a successful cap.set() the camera needs settle time before read-back
# (spec §5 / §7: sleep(0.5) x3).
_SET_VERIFY_SETTLE = 0.5

# Probe range for the OpenCV backend (spec §3.3: indices 0..4 inclusive).
_PROBE_INDICES = range(0, 5)

# Legacy error message strings (spec §6, element -1 table).
_ERR_NO_CAMERA = "Cannot find any camera."
_ERR_TAKE_PICTURE = "Could not take picture."

CaptureFactory = Callable[[int], Any]
"""A callable ``factory(index) -> capture`` returning an object with the
OpenCV ``VideoCapture`` surface (``isOpened``/``read``/``set``/``get``/
``release``). Injecting one makes the probe testable without OpenCV."""


@dataclass(frozen=True)
class Frame:
    """A single captured frame.

    Attributes:
        image: The pixel data. For the OpenCV backend this is the native cv2
            frame (an ``(H, W, 3)`` BGR ndarray) from :meth:`Camera.capture`,
            or a grayscale ``(H, W)`` array from :meth:`Camera.capture_gray`.
            For the simulated backend it is a grayscale ndarray (or a
            :class:`SimpleFrame` stand-in when numpy is unavailable).
        timestamp: Wall-clock capture time (``time.time()`` seconds).
        index: Monotonic per-open frame counter.
    """

    image: Any
    timestamp: float
    index: int


class SimpleFrame:
    """Minimal ndarray stand-in used when numpy is unavailable.

    Provides just enough surface (``shape``, indexing into ``data``) for the
    simulated backend to produce and report frames without numpy.
    """

    def __init__(self, width: int, height: int, fill: int = 0) -> None:
        self.width = width
        self.height = height
        #: ``(height, width)`` -- ndarray-compatible ``shape``.
        self.shape: Tuple[int, int] = (height, width)
        #: Row-major pixel data, ``data[row][col]``.
        self.data: List[List[int]] = [[fill] * width for _ in range(height)]

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SimpleFrame(width={self.width}, height={self.height})"


def _frame_wh(frame: Any) -> Optional[Tuple[int, int]]:
    """Return ``(width, height)`` inferred from a frame's shape, or None."""
    shape = getattr(frame, "shape", None)
    if shape is not None and len(shape) >= 2:
        # ndarray / SimpleFrame shape is (height, width, ...)
        return int(shape[1]), int(shape[0])
    return None


def to_grayscale(image: Any) -> Any:
    """Convert a frame to single-channel grayscale.

    Uses ``cv2.COLOR_BGR2GRAY`` when OpenCV is available and the image is
    3-channel (the rewrite fixes the legacy ``COLOR_RGB2GRAY``-on-BGR quirk,
    spec §4). Falls back to a numpy channel mean, and finally returns the
    image unchanged when it is already single-channel or a stand-in.

    Args:
        image: A BGR or grayscale frame.

    Returns:
        A grayscale representation of ``image``.
    """
    ndim = getattr(image, "ndim", None)
    if ndim == 3:
        if cv2 is not None:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if np is not None:
            return image.mean(axis=2).astype("uint8")
    return image


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
class _OpenCVBackend:
    """Real camera backend over ``cv2.VideoCapture`` (spec §3, §4, §5)."""

    def __init__(
        self,
        index: Optional[int],
        resolution_hint: Optional[Tuple[int, int]],
        api_preference: Optional[int],
        gain: Optional[float],
        exposure: Optional[float],
        fps: Optional[float],
        capture_factory: Optional[CaptureFactory],
        logger: logging.Logger,
    ) -> None:
        self._index = index
        self._resolution_hint = resolution_hint
        self._api_preference = api_preference
        self._gain = gain
        self._exposure = exposure
        self._fps = fps
        self._capture_factory = capture_factory
        self._logger = logger

        self._lock = threading.RLock()
        self._cap: Any = None
        self._selected_index: Optional[int] = None
        self._effective_resolution: Optional[Tuple[int, int]] = None
        self._frame_index = 0

    # -- factory ----------------------------------------------------------
    def _make_capture(self, index: int) -> Any:
        """Build a capture object for ``index`` (injected factory or cv2)."""
        if self._capture_factory is not None:
            return self._capture_factory(index)
        if cv2 is None:
            # cv2 is only required here -- the moment the real OpenCV backend
            # is actually exercised without an injected factory (spec §1 /
            # brief "optional-dependency modules").
            raise CameraError(
                "The OpenCV camera backend requires OpenCV, which is not "
                "installed. Install it with: pip install sciglob[camera]"
            )
        api = self._api_preference if self._api_preference is not None else cv2.CAP_ANY
        return cv2.VideoCapture(index, api)

    # -- lifecycle --------------------------------------------------------
    def open(self) -> None:
        """Probe indices and accept the first frame-delivering device.

        Spec §3.3: never reject on resolution mismatch; store the effective
        resolution read back from the accepted device.

        Raises:
            CameraError: If no probed index delivers a frame.
        """
        with self._lock:
            if self._cap is not None:
                return
            indices = [self._index] if self._index is not None else list(_PROBE_INDICES)
            for i in indices:
                cap = self._make_capture(i)
                try:
                    is_open = bool(cap.isOpened())
                except Exception:  # pragma: no cover - defensive
                    is_open = False
                if not is_open:
                    self._safe_release(cap)
                    continue

                # Request the configured resolution as a HINT only (return
                # values deliberately ignored; spec §3.1 step 4).
                if self._resolution_hint is not None:
                    w_hint, h_hint = self._resolution_hint
                    cap.set(_PROP_FRAME_WIDTH, w_hint)
                    cap.set(_PROP_FRAME_HEIGHT, h_hint)

                # Validate the device by actually reading a frame (spec §3.3:
                # "delivers a frame" validated with a real read()).
                try:
                    ok, frame = cap.read()
                except Exception:  # pragma: no cover - defensive
                    ok, frame = False, None
                if not ok or frame is None:
                    self._safe_release(cap)
                    continue

                # Accept this device; store EFFECTIVE resolution (not hint).
                self._cap = cap
                self._selected_index = i
                self._effective_resolution = self._read_effective_resolution(cap, frame)
                self._frame_index = 0
                self._logger.info(
                    "Opened OpenCV camera at index %d, effective resolution %s",
                    i,
                    self._effective_resolution,
                )
                self._apply_optional_settings()
                return

            raise CameraError(_ERR_NO_CAMERA)

    def _read_effective_resolution(self, cap: Any, frame: Any) -> Tuple[int, int]:
        """Read back the device's effective resolution (spec §3.1 step 5)."""
        try:
            w = int(round(float(cap.get(_PROP_FRAME_WIDTH))))
            h = int(round(float(cap.get(_PROP_FRAME_HEIGHT))))
        except Exception:  # pragma: no cover - defensive
            w = h = 0
        if w > 0 and h > 0:
            return (w, h)
        # Fall back to the shape of the frame we just read.
        wh = _frame_wh(frame)
        if wh is not None:
            return wh
        return self._resolution_hint or (0, 0)

    def _apply_optional_settings(self) -> None:
        """Set gain/exposure/fps when configured; skip silently otherwise.

        Spec §5: set -> sleep(0.5) -> verify per property. For FPS the
        *effective* value is stored back (spec §5 step 3).
        """
        if self._gain is not None:
            self._set_verify(_PROP_GAIN, self._gain, "gain")
        if self._exposure is not None:
            self._set_verify(_PROP_EXPOSURE, self._exposure, "exposure")
        if self._fps is not None:
            ok = self._set_verify(_PROP_FPS, self._fps, "fps")
            if not ok:
                try:
                    self._fps = float(self._cap.get(_PROP_FPS))
                except Exception:  # pragma: no cover - defensive
                    pass

    def _set_verify(self, prop: int, value: float, label: str) -> bool:
        """cap.set -> settle -> cap.get read-back; log capability outcome."""
        try:
            ok = bool(self._cap.set(prop, value))
        except Exception:  # pragma: no cover - defensive
            ok = False
        if not ok:
            self._logger.debug("Camera %s not settable", label)
            return False
        time.sleep(_SET_VERIFY_SETTLE)
        try:
            readback = float(self._cap.get(prop))
        except Exception:  # pragma: no cover - defensive
            readback = float("nan")
        settled = readback == float(value)
        if not settled:
            self._logger.debug(
                "Camera %s set to %s but read back %s", label, value, readback
            )
        return settled

    def capture(self) -> Frame:
        """Capture a native (BGR) frame using the warm-up double-read.

        Spec §4: two consecutive reads; the first discards the stale buffered
        frame.

        Raises:
            CameraError: If the camera is not open or the read fails.
        """
        with self._lock:
            cap = self._require_open()
            cap.read()  # discard stale warm-up frame (spec §4)
            try:
                ok, frame = cap.read()
            except Exception as exc:  # pragma: no cover - defensive
                raise CameraError(_ERR_TAKE_PICTURE) from exc
            if not ok or frame is None:
                raise CameraError(_ERR_TAKE_PICTURE)
            idx = self._frame_index
            self._frame_index += 1
            return Frame(image=frame, timestamp=time.time(), index=idx)

    @property
    def effective_resolution(self) -> Optional[Tuple[int, int]]:
        return self._effective_resolution

    @property
    def selected_index(self) -> Optional[int]:
        return self._selected_index

    def is_open(self) -> bool:
        with self._lock:
            if self._cap is None:
                return False
            is_opened = getattr(self._cap, "isOpened", None)
            if callable(is_opened):
                try:
                    return bool(is_opened())
                except Exception:  # pragma: no cover - defensive
                    return False
            return True

    def release(self) -> None:
        """Release the capture device. Idempotent and exception-proof."""
        with self._lock:
            if self._cap is not None:
                self._safe_release(self._cap)
                self._cap = None

    def _require_open(self) -> Any:
        if self._cap is None:
            raise CameraError("Camera is not open; call open() first.")
        return self._cap

    @staticmethod
    def _safe_release(cap: Any) -> None:
        release = getattr(cap, "release", None)
        if callable(release):
            try:
                release()
            except Exception:  # pragma: no cover - defensive
                pass


class _SimulatedBackend:
    """Zero-dependency simulated backend (spec §8).

    Generates a synthetic sun disk (legacy math: center jitter 1%, radius
    10 px, spot value 200 on a 0 background) or cycles a canned frame list.
    Reports the *requested* resolution as the effective resolution.
    """

    def __init__(
        self,
        resolution: Tuple[int, int],
        spot_center: Optional[Tuple[float, float]],
        spot_radius: float,
        spot_value: int,
        jitter: float,
        frames: Optional[List[Any]],
        logger: logging.Logger,
    ) -> None:
        self._resolution = resolution
        self._spot_center = spot_center
        self._spot_radius = spot_radius
        self._spot_value = spot_value
        self._jitter = jitter
        self._frames = frames
        self._logger = logger

        self._lock = threading.RLock()
        self._is_open = False
        self._frame_index = 0
        self._next = 0
        #: Ground-truth spot center of the last generated frame (spec §8:
        #: "needed for tests only"). ``(x, y)`` in pixels.
        self.last_true_center: Optional[Tuple[float, float]] = None

    def open(self) -> None:
        with self._lock:
            self._is_open = True
            self._frame_index = 0
            self._logger.info(
                "Opened simulated camera at resolution %s", self._resolution
            )

    def capture(self) -> Frame:
        with self._lock:
            if not self._is_open:
                raise CameraError("Camera is not open; call open() first.")
            image = self._generate()
            idx = self._frame_index
            self._frame_index += 1
            return Frame(image=image, timestamp=time.time(), index=idx)

    def _generate(self) -> Any:
        if self._frames is not None:
            if not self._frames:
                raise CameraError(_ERR_TAKE_PICTURE)
            frame = self._frames[self._next % len(self._frames)]
            self._next += 1
            return frame

        w, h = self._resolution
        jitter = self._jitter
        if self._spot_center is not None:
            cx = self._spot_center[0] * (1.0 + random.gauss(0.0, 1.0) * jitter)
            cy = self._spot_center[1] * (1.0 + random.gauss(0.0, 1.0) * jitter)
        else:
            cx = w * (0.5 + random.gauss(0.0, 1.0) * jitter)
            cy = h * (0.5 + random.gauss(0.0, 1.0) * jitter)
        self.last_true_center = (cx, cy)
        r2 = self._spot_radius * self._spot_radius

        if np is not None:
            yy, xx = np.ogrid[:h, :w]
            mask = (xx - cx) ** 2 + (yy - cy) ** 2 < r2
            arr = np.zeros((h, w), dtype=np.uint8)
            arr[mask] = self._spot_value
            return arr

        frame = SimpleFrame(w, h, fill=0)
        r = int(self._spot_radius) + 1
        row_lo = max(0, int(cy) - r)
        row_hi = min(h, int(cy) + r + 1)
        col_lo = max(0, int(cx) - r)
        col_hi = min(w, int(cx) + r + 1)
        for row in range(row_lo, row_hi):
            for col in range(col_lo, col_hi):
                if (col - cx) ** 2 + (row - cy) ** 2 < r2:
                    frame.data[row][col] = self._spot_value
        return frame

    @property
    def effective_resolution(self) -> Optional[Tuple[int, int]]:
        # Simulated backend reports the requested resolution (spec §8).
        return self._resolution

    @property
    def selected_index(self) -> Optional[int]:
        return None

    def is_open(self) -> bool:
        with self._lock:
            return self._is_open

    def release(self) -> None:
        with self._lock:
            self._is_open = False


# ---------------------------------------------------------------------------
# Public frontend
# ---------------------------------------------------------------------------
class Camera:
    """Unified camera frontend dispatching to one of two backends.

    Args:
        backend: ``"opencv"`` (real, needs OpenCV), ``"simulated"`` (no
            extras), or ``"directx"`` (alias for OpenCV with the ``CAP_DSHOW``
            DirectShow preference).
        index: OpenCV device index to open; ``None`` probes indices 0-4.
        resolution: Requested ``(width, height)``. For OpenCV this is a hint
            only (the effective resolution is stored after open); for the
            simulated backend it is authoritative.
        api_preference: OpenCV backend hint (e.g. ``cv2.CAP_DSHOW``).
        gain: Optional OpenCV gain; skipped silently when ``None``.
        exposure: Optional OpenCV exposure; skipped silently when ``None``.
        fps: Optional OpenCV frame rate; skipped silently when ``None``.
        capture_factory: Optional ``factory(index) -> capture`` used by the
            OpenCV backend instead of ``cv2.VideoCapture`` -- lets tests drive
            the probe without OpenCV installed.
        name: Logger name suffix (``sciglob.<name>``).
        spot_center: Simulated backend: sun-disk center ``(x, y)``; ``None``
            centers on the frame.
        spot_radius: Simulated backend: sun-disk radius in pixels.
        spot_value: Simulated backend: fill value inside the disk.
        jitter: Simulated backend: fractional center jitter.
        frames: Simulated backend: canned frame list to cycle instead of
            generating a synthetic sun.

    Raises:
        CameraError: On an unknown backend, when the OpenCV backend is used
            without OpenCV (and no ``capture_factory``), or on capture/probe
            failure.
    """

    def __init__(
        self,
        backend: str = "opencv",
        index: Optional[int] = None,
        resolution: Optional[Tuple[int, int]] = (640, 480),
        api_preference: Optional[int] = None,
        gain: Optional[float] = None,
        exposure: Optional[float] = None,
        fps: Optional[float] = None,
        capture_factory: Optional[CaptureFactory] = None,
        name: str = "Camera",
        spot_center: Optional[Tuple[float, float]] = None,
        spot_radius: float = 10,
        spot_value: int = 200,
        jitter: float = 0.01,
        frames: Optional[List[Any]] = None,
    ) -> None:
        self.logger = logging.getLogger(f"sciglob.{name}")
        self._backend_name = backend.lower()
        self._backend: Any

        if self._backend_name in ("opencv", "cv2", "directx"):
            # "directx" is a compatibility alias -> OpenCV + DirectShow.
            if (
                self._backend_name == "directx"
                and api_preference is None
                and cv2 is not None
            ):
                api_preference = cv2.CAP_DSHOW
            elif (
                self._backend_name == "opencv"
                and api_preference is None
                and cv2 is not None
                and platform.system() == "Windows"
            ):
                # Spec §12 / Pandora2.0: prefer stable DirectShow on Windows.
                api_preference = cv2.CAP_DSHOW
            self._backend = _OpenCVBackend(
                index=index,
                resolution_hint=resolution,
                api_preference=api_preference,
                gain=gain,
                exposure=exposure,
                fps=fps,
                capture_factory=capture_factory,
                logger=self.logger,
            )
        elif self._backend_name in ("simulated", "simul", "sim"):
            self._backend = _SimulatedBackend(
                resolution=resolution or (640, 480),
                spot_center=spot_center,
                spot_radius=spot_radius,
                spot_value=spot_value,
                jitter=jitter,
                frames=frames,
                logger=self.logger,
            )
        else:
            raise CameraError(f"Unknown camera backend: {backend!r}")

    # -- lifecycle --------------------------------------------------------
    def open(self) -> "Camera":
        """Open (and, for OpenCV, probe) the camera.

        Returns:
            ``self`` so the call chains.
        """
        self._backend.open()
        return self

    def capture(self) -> Frame:
        """Capture a native frame (BGR for OpenCV) using the double-read."""
        return cast(Frame, self._backend.capture())

    def capture_gray(self) -> Frame:
        """Capture a frame and return it converted to grayscale."""
        frame = self._backend.capture()
        return Frame(
            image=to_grayscale(frame.image),
            timestamp=frame.timestamp,
            index=frame.index,
        )

    @property
    def effective_resolution(self) -> Optional[Tuple[int, int]]:
        """Effective ``(width, height)`` after :meth:`open` (None before)."""
        return cast(Optional[Tuple[int, int]], self._backend.effective_resolution)

    @property
    def selected_index(self) -> Optional[int]:
        """The device index accepted by the OpenCV probe (None if N/A)."""
        return cast(Optional[int], self._backend.selected_index)

    @property
    def backend(self) -> str:
        """The resolved backend name."""
        return self._backend_name

    def is_open(self) -> bool:
        """Whether the camera is currently open."""
        return bool(self._backend.is_open())

    def release(self) -> None:
        """Release the camera. Idempotent and exception-proof (spec §9.3)."""
        self._backend.release()

    # -- context manager --------------------------------------------------
    def __enter__(self) -> "Camera":
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()


class SimulatedCamera(Camera):
    """Convenience :class:`Camera` pinned to the simulated backend (spec §8).

    Generates a synthetic sun disk (or cycles ``frames``) and reports the
    requested resolution as the effective resolution -- no extras required.
    """

    def __init__(
        self,
        resolution: Tuple[int, int] = (640, 480),
        spot_center: Optional[Tuple[float, float]] = None,
        spot_radius: float = 10,
        spot_value: int = 200,
        jitter: float = 0.01,
        frames: Optional[List[Any]] = None,
        name: str = "SimulatedCamera",
    ) -> None:
        super().__init__(
            backend="simulated",
            resolution=resolution,
            spot_center=spot_center,
            spot_radius=spot_radius,
            spot_value=spot_value,
            jitter=jitter,
            frames=frames,
            name=name,
        )

    @property
    def last_true_center(self) -> Optional[Tuple[float, float]]:
        """Ground-truth center of the last generated frame (tests only)."""
        return cast(Optional[Tuple[float, float]], self._backend.last_true_center)


class OpenCVCamera(Camera):
    """Convenience :class:`Camera` pinned to the real OpenCV backend."""

    def __init__(
        self,
        index: Optional[int] = None,
        resolution: Optional[Tuple[int, int]] = (640, 480),
        api_preference: Optional[int] = None,
        gain: Optional[float] = None,
        exposure: Optional[float] = None,
        fps: Optional[float] = None,
        capture_factory: Optional[CaptureFactory] = None,
        name: str = "OpenCVCamera",
    ) -> None:
        super().__init__(
            backend="opencv",
            index=index,
            resolution=resolution,
            api_preference=api_preference,
            gain=gain,
            exposure=exposure,
            fps=fps,
            capture_factory=capture_factory,
            name=name,
        )

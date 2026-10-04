"""Attrappen fuer Kamera, Tracker und virtuelle Kamera (Tests ohne Hardware)."""
import threading
import time

import numpy as np

from fake_face import make_face
from gesichtsfilter.io.camera import CameraError
from gesichtsfilter.io.vcam import VirtualCamError


class FakeGrabber:
    """Wie CameraGrabber: ein Thread liefert ca. 30 Bilder/s, wait_frame wartet aufs neueste."""
    fail = False

    def __init__(self, info):
        if FakeGrabber.fail:
            raise CameraError("Test: Kamera belegt")
        self.info, self.error = info, None
        self.width, self.height = 640, 360
        self._id = 0
        self._frame = np.full((360, 640, 3), (90, 110, 70), np.uint8)
        self._cond = threading.Condition()
        self._running = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        self.closed = False

    def _loop(self):
        while self._running:
            time.sleep(1 / 30)
            with self._cond:
                self._id += 1
                self._cond.notify_all()

    def wait_frame(self, last_id, timeout=0.2):
        with self._cond:
            if self._id == last_id:
                self._cond.wait(timeout)
            if self._id == last_id:
                return None, last_id
            return self._frame, self._id

    def close(self):
        self._running = False
        self._t.join(timeout=1)
        self.closed = True


class FakeTracker:
    delegate_used = "CPU"
    note = ""
    explode = False

    def __init__(self, use_gpu=False):
        self.use_gpu, self.closed = use_gpu, False

    def detect(self, bgr):
        if FakeTracker.explode:
            raise RuntimeError("Test-Absturz im Tracker")
        return make_face(0.5, 0.4, aspect=640 / 360)

    def close(self):
        self.closed = True


class FakeVcam:
    fail = False

    def __init__(self):
        self.frames, self._on, self.device = [], False, "Fake Virtual Camera"
        self.started_with = None

    @property
    def active(self):
        return self._on

    def start(self, w, h, fps, backend=None, device=None):
        self.started_with = (backend, device)
        if FakeVcam.fail:
            raise VirtualCamError("Test: OBS fehlt")
        self._on, self.size = True, (w, h)

    def send(self, frame):
        self.frames.append(frame.shape)

    def stop(self):
        self._on = False

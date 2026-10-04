"""Kamera: Auflisten und Auslesen in eigenem Thread (immer das neueste Bild)."""
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2

# Unter Windows DirectShow (schnell, stabil bei Webcams), sonst OpenCV-Standard
BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
CAPTURE_SIZE = (1280, 720)
CAPTURE_FPS = 30
# Kameras mit diesen Namensteilen werden nicht angeboten (Rueckkopplung!)
BLOCKED_NAMES = ("obs virtual", "obs-camera", "virtual camera")


class CameraError(RuntimeError):
    """Kamera nicht oeffenbar oder ausgefallen (Text ist fuer Anwender gedacht)."""


@dataclass
class CameraInfo:
    name: str
    index: int
    backend: int


def list_cameras(max_probe: int = 5) -> List[CameraInfo]:
    """Findet Kameras. Mit Namen, falls cv2-enumerate-cameras verfuegbar ist."""
    found: List[CameraInfo] = []
    try:
        from cv2_enumerate_cameras import enumerate_cameras
        for c in enumerate_cameras(BACKEND):
            found.append(CameraInfo(c.name, c.index, c.backend))
    except Exception:
        found = []
    if not found:  # Fallback: Indizes durchprobieren
        for i in range(max_probe):
            cap = cv2.VideoCapture(i, BACKEND)
            ok = cap.isOpened()
            cap.release()
            if ok:
                found.append(CameraInfo(f"Kamera {i}", i, BACKEND))
    return [c for c in found if not any(b in c.name.lower() for b in BLOCKED_NAMES)]


class CameraGrabber:
    """Liest in einem Hintergrund-Thread dauernd Bilder und behaelt nur das neueste.

    So staut sich nichts im Kamerapuffer, auch wenn Tracking/Rendering mal laenger dauert.
    """

    def __init__(self, info: CameraInfo, size: Tuple[int, int] = CAPTURE_SIZE,
                 fps: int = CAPTURE_FPS):
        self.info = info
        self.error: Optional[str] = None
        self._cap = cv2.VideoCapture(info.index, info.backend)
        if not self._cap.isOpened():
            self._cap.release()
            raise CameraError(
                f"Die Kamera \u201e{info.name}\u201c konnte nicht ge\u00f6ffnet werden.\n"
                "Wird sie gerade von einem anderen Programm benutzt?")
        # MJPG liefert bei vielen Webcams erst 720p mit 30 fps
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, first = self._cap.read()
        if not ok or first is None:
            self._cap.release()
            raise CameraError(f"Die Kamera \u201e{info.name}\u201c liefert kein Bild.")
        self.height, self.width = first.shape[:2]
        self._frame = first
        self._id = 1
        self._cond = threading.Condition()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="Kamera-Lesen", daemon=True)
        self._thread.start()

    def _loop(self):
        fails = 0
        while self._running:
            ok, f = self._cap.read()
            if not ok or f is None:
                fails += 1
                if fails > 60:
                    with self._cond:
                        self.error = "Das Kamerabild ist ausgefallen (Kamera getrennt?)."
                        self._cond.notify_all()
                    return
                continue
            fails = 0
            with self._cond:
                self._frame = f
                self._id += 1
                self._cond.notify_all()

    def wait_frame(self, last_id: int, timeout: float = 0.2):
        """Wartet auf ein Bild, das neuer ist als last_id. -> (frame, id) oder (None, last_id)."""
        with self._cond:
            if self._id == last_id and self.error is None:
                self._cond.wait(timeout)
            if self._id == last_id:
                return None, last_id
            return self._frame, self._id

    def close(self):
        self._running = False
        self._thread.join(timeout=1.5)
        self._cap.release()

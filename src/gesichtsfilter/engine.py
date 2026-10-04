"""Verarbeitungs-Thread: Kamera -> Tracking -> Rendering -> virtuelle Kamera + Vorschau.

Die Oberflaeche (Haupt-Thread) bleibt davon unberuehrt. Kommunikation:
  * UI -> Engine:  Methoden wie open_camera(), set_vcam() (thread-sicher, per Warteschlange)
  * Engine -> UI:  Qt-Signale (werden automatisch in den UI-Thread uebergeben)
Settings und Assets werden direkt als gemeinsame Objekte gelesen (einfache
Zuweisungen sind in Python atomar; ein Frame mit halb geaendertem Wert ist harmlos).
"""
import logging
import queue
import time
from typing import Callable, Optional

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from . import config as C
from .core.pipeline import Pipeline
from .core.settings import RigAssets, Settings
from .io.camera import CameraError, CameraGrabber, CameraInfo
from .io.vcam import VirtualCamera, VirtualCamError

log = logging.getLogger(__name__)

PREVIEW_FPS = 20          # Vorschau wird hoechstens so oft aktualisiert
PREVIEW_MAX_WIDTH = 960   # Vorschau wird vor der Uebergabe an die UI verkleinert


def _default_tracker_factory(use_gpu: bool):
    from .core.tracker import FaceTracker
    return FaceTracker(use_gpu=use_gpu)


class Engine(QThread):
    previewReady = Signal(QImage)
    status = Signal(str)                 # kurze Statusmeldung
    stats = Signal(float, float, float)  # fps, Tracking-ms, Render-ms
    errorOccurred = Signal(str, str)     # Titel, Text
    cameraStarted = Signal(int, int)     # Breite, Hoehe
    cameraStopped = Signal()
    vcamChanged = Signal(bool, str)      # aktiv, Geraetename

    def __init__(self, settings: Settings, assets: RigAssets,
                 tracker_factory: Callable = _default_tracker_factory,
                 grabber_factory: Callable = CameraGrabber,
                 vcam_factory: Callable = VirtualCamera):
        super().__init__()
        self.settings, self.assets = settings, assets
        self._tracker_factory = tracker_factory
        self._grabber_factory = grabber_factory
        self.vcam = vcam_factory()
        self.fps_limit = C.DEFAULT_FPS
        self.use_gpu = False
        self.preview_enabled = True
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._stop = False
        self._grabber = None
        self._tracker = None
        self._tracker_gpu = None
        self._pipeline: Optional[Pipeline] = None
        self._last_id = 0
        self._want_vcam = False
        self._last_error = ""

    # ------------------------------------------------------------ UI-Seite
    def open_camera(self, info: CameraInfo): self._q.put(("open", info))
    def close_camera(self): self._q.put(("close", None))
    def set_vcam(self, on: bool): self._q.put(("vcam", on))
    def request_rest_pose(self): self._q.put(("rest", None))
    def set_gpu(self, on: bool): self._q.put(("gpu", on))

    def shutdown(self):
        self._stop = True
        self.wait(4000)

    # ------------------------------------------------------------ Thread
    def run(self):
        stat_t, stat_n = time.perf_counter(), 0
        prev_t = 0.0
        while not self._stop:
            self._drain()
            g = self._grabber
            if g is None:
                self.msleep(30)
                continue
            frame, fid = g.wait_frame(self._last_id, 0.2)
            if g.error:
                self._fail("Kamera", g.error)
                self._close_camera()
                continue
            if frame is None:
                continue
            self._last_id = fid
            t0 = time.perf_counter()
            try:
                out = self._pipeline.process(frame)
            except Exception as e:  # nie den Thread sterben lassen
                log.exception("Fehler beim Verarbeiten")
                self._fail_once("Fehler im Filter", f"{type(e).__name__}: {e}")
                out = cv2.flip(frame, 1) if self.settings.mirror else frame
            if self.vcam.active:
                try:
                    self.vcam.send(out)
                except Exception as e:
                    self.vcam.stop()
                    self.vcamChanged.emit(False, "")
                    self._fail("Virtuelle Kamera", f"Senden fehlgeschlagen und gestoppt:\n{e}")
            now = time.perf_counter()
            if self.preview_enabled and now - prev_t >= 1.0 / PREVIEW_FPS:
                prev_t = now
                self.previewReady.emit(self._to_qimage(out))
            stat_n += 1
            if now - stat_t >= 1.0:
                self.stats.emit(stat_n / (now - stat_t), self._pipeline.last_track_ms,
                                self._pipeline.last_render_ms)
                stat_t, stat_n = now, 0
            # fps-Limit: Rest des Frame-Budgets schlafen (schont CPU fuers Spiel)
            rest = 1.0 / max(1, self.fps_limit) - (time.perf_counter() - t0)
            if rest > 0.001:
                self.msleep(int(rest * 1000))
        self._close_camera()
        self._close_tracker()

    # ------------------------------------------------------------ intern
    def _drain(self):
        while True:
            try:
                cmd, arg = self._q.get_nowait()
            except queue.Empty:
                return
            try:
                if cmd == "open": self._open(arg)
                elif cmd == "close": self._close_camera()
                elif cmd == "vcam": self._vcam(arg)
                elif cmd == "rest" and self._pipeline: self._pipeline.rig.set_rest_pose()
                elif cmd == "gpu": self._set_gpu(arg)
            except Exception as e:
                log.exception("Befehl %s fehlgeschlagen", cmd)
                self._fail("Fehler", str(e))

    def _open(self, info: CameraInfo):
        self._close_camera()
        self.status.emit("Lade Gesichtsmodell \u2026")
        try:
            self._ensure_tracker()
        except Exception as e:
            self._fail("Gesichtsmodell", str(e))
            self.status.emit("Bereit.")
            return
        self.status.emit(f"\u00d6ffne Kamera \u201e{info.name}\u201c \u2026")
        try:
            self._grabber = self._grabber_factory(info)
        except CameraError as e:
            self._fail("Kamera", str(e))
            self.status.emit("Bereit.")
            return
        if self._pipeline is None:
            self._pipeline = Pipeline(self._tracker, self.settings, self.assets)
        else:
            self._pipeline.tracker = self._tracker
            self._pipeline.reset()
        self._last_id = 0
        self.cameraStarted.emit(self._grabber.width, self._grabber.height)
        note = getattr(self._tracker, "note", "")
        delegate = getattr(self._tracker, "delegate_used", "CPU")
        self.status.emit(f"L\u00e4uft ({delegate}). Sitz gerade und klicke \u201eRuhelage setzen\u201c."
                         + (f" {note}" if note else ""))

    def _close_camera(self):
        if self.vcam.active:
            self.vcam.stop()
            self.vcamChanged.emit(False, "")
        if self._grabber is not None:
            self._grabber.close()
            self._grabber = None
            self.cameraStopped.emit()
            self.status.emit("Kamera gestoppt.")

    def _ensure_tracker(self):
        if self._tracker is not None and self._tracker_gpu == self.use_gpu:
            return
        self._close_tracker()
        self._tracker = self._tracker_factory(self.use_gpu)
        self._tracker_gpu = self.use_gpu

    def _close_tracker(self):
        if self._tracker is not None and hasattr(self._tracker, "close"):
            self._tracker.close()
        self._tracker = None

    def _set_gpu(self, on: bool):
        self.use_gpu = on
        if self._grabber is not None:   # laeuft schon: Tracker neu aufbauen
            self.status.emit("Wechsle Tracking-Modus \u2026")
            self._ensure_tracker()
            self._pipeline.tracker = self._tracker
            self.status.emit(f"Tracking l\u00e4uft auf: {getattr(self._tracker, 'delegate_used', 'CPU')}. "
                             + getattr(self._tracker, "note", ""))

    def _vcam(self, on: bool):
        if not on:
            if self.vcam.active:
                self.vcam.stop()
            self.vcamChanged.emit(False, "")
            return
        if self._grabber is None:
            self.vcamChanged.emit(False, "")      # erst Zustand, dann Meldung
            self._fail("Virtuelle Kamera", "Bitte zuerst die Kamera starten.")
            return
        try:
            self.vcam.start(self._grabber.width, self._grabber.height, self.fps_limit)
        except VirtualCamError as e:
            self.vcamChanged.emit(False, "")
            self._fail("Virtuelle Kamera", str(e))
            return
        self.vcamChanged.emit(True, self.vcam.device)

    @staticmethod
    def _to_qimage(bgr: np.ndarray) -> QImage:
        h, w = bgr.shape[:2]
        if w > PREVIEW_MAX_WIDTH:
            bgr = cv2.resize(bgr, (PREVIEW_MAX_WIDTH, round(h * PREVIEW_MAX_WIDTH / w)),
                             interpolation=cv2.INTER_AREA)
            h, w = bgr.shape[:2]
        bgr = np.ascontiguousarray(bgr)
        return QImage(bgr.data, w, h, bgr.strides[0], QImage.Format.Format_BGR888).copy()

    def _fail(self, title: str, text: str):
        self.errorOccurred.emit(title, text)

    def _fail_once(self, title: str, text: str):
        if text != self._last_error:    # gleiche Meldung nicht 30x pro Sekunde
            self._last_error = text
            self._fail(title, text)

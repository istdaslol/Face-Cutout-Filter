"""Gesichts-Tracking mit MediaPipe FaceLandmarker (Modell lokal, kein Download)."""
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from .. import config as C
from ..paths import MODEL_REL, resource


class TrackerError(RuntimeError):
    """Modell fehlt oder MediaPipe laesst sich nicht starten."""


class FaceTracker:
    """Liefert pro Bild die 478 Landmarks (normalisiert 0..1) oder None.

    Das Tracking laeuft auf einem verkleinerten Bild (track_size); da die
    Landmarks normalisiert sind, gilt das Ergebnis auch fuer die volle Aufloesung.
    """

    def __init__(self, use_gpu: bool = False, track_size: Tuple[int, int] = C.TRACK_SIZE,
                 model_path=None):
        self.track_size = track_size
        self.delegate_used = "CPU"
        self.note = ""
        path = model_path or resource(MODEL_REL)
        if not path.exists():
            raise TrackerError(
                f"Gesichtsmodell nicht gefunden: {path}\n"
                "Bitte 'python tools/fetch_model.py' ausfuehren bzw. neu installieren.")
        try:
            import mediapipe as mp  # spaet importieren: Tests ohne MediaPipe moeglich
            from mediapipe.tasks.python import BaseOptions, vision
        except Exception as e:  # pragma: no cover
            raise TrackerError(f"MediaPipe konnte nicht geladen werden: {e}") from e
        self._mp = mp
        # Modell als Bytes uebergeben: robust gegen Umlaute/Sonderzeichen im Pfad
        buf = path.read_bytes()

        def make(delegate):
            opts = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_buffer=buf, delegate=delegate),
                running_mode=vision.RunningMode.VIDEO, num_faces=1)
            return vision.FaceLandmarker.create_from_options(opts)

        self._lm = None
        if use_gpu:
            try:
                self._lm = make(BaseOptions.Delegate.GPU)
                self.delegate_used = "GPU"
            except Exception:
                self.note = "GPU nicht verfuegbar, es wird die CPU verwendet."
        if self._lm is None:
            try:
                self._lm = make(BaseOptions.Delegate.CPU)
            except Exception as e:  # pragma: no cover
                raise TrackerError(f"Gesichtsmodell konnte nicht gestartet werden: {e}") from e
        self._ts = 0

    def detect(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        """Landmarks (478, 2) float32 normalisiert, oder None."""
        H, W = bgr.shape[:2]
        tw, th = self.track_size
        f = min(tw / W, th / H, 1.0)
        small = cv2.resize(bgr, (max(1, round(W * f)), max(1, round(H * f))),
                           interpolation=cv2.INTER_AREA) if f < 1.0 else bgr
        rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        self._ts = max(self._ts + 1, int(time.monotonic() * 1000))  # streng monoton
        res = self._lm.detect_for_video(img, self._ts)
        if not res.face_landmarks:
            return None
        return np.array([[p.x, p.y] for p in res.face_landmarks[0]], dtype=np.float32)

    def close(self) -> None:
        if self._lm is not None:
            self._lm.close()
            self._lm = None

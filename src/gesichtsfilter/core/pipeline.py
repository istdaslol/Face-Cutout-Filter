"""Pipeline: Tracking (evtl. nur jeden 2. Frame) -> Glaettung -> Rig."""
import time
from typing import Optional, Protocol

import numpy as np

from .. import config as C
from .rig import Rig
from .settings import RigAssets, Settings


class _Tracker(Protocol):
    def detect(self, bgr: np.ndarray) -> Optional[np.ndarray]: ...


class Pipeline:
    """Ein Frame rein, ein fertiges Frame raus. Kein UI, keine Threads."""

    def __init__(self, tracker: _Tracker, settings: Optional[Settings] = None,
                 assets: Optional[RigAssets] = None):
        self.tracker = tracker
        self.settings = settings or Settings()
        self.assets = assets or RigAssets()
        self.rig = Rig()
        self._n = 0
        self.last_track_ms = 0.0    # Zeit fuer Tracking + Glaettung (letzter Frame)
        self.last_render_ms = 0.0   # Zeit fuer das Rendern
        self._reset_tracking()

    def _reset_tracking(self):
        self._last = None      # letzte Detektion
        self._prev = None      # vorletzte Detektion
        self._smooth = None    # geglaettete Landmarks

    def reset(self):
        """Nach Kamerawechsel: Ruhelage und Glaettung vergessen."""
        self.rig.reset()
        self._reset_tracking()
        self._n = 0

    def _target(self, cam: np.ndarray) -> Optional[np.ndarray]:
        stride = max(1, int(self.settings.track_every))
        run = (self._n % stride == 0)
        self._n += 1
        if run:
            det = self.tracker.detect(cam)
            if det is None:
                self._reset_tracking()
                return None
            self._prev, self._last = self._last, det
            return det
        # Uebersprungener Frame: Bewegung um einen halben Schritt fortschreiben
        if self._last is None:
            return None
        if self._prev is None:
            return self._last
        return self._last + (self._last - self._prev) * 0.5

    def process(self, cam_bgr: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        target = self._target(cam_bgr)
        if target is None:
            self._smooth = None
            lm = None
        else:
            k = C.SMOOTHING
            self._smooth = target if self._smooth is None else self._smooth + (target - self._smooth) * k
            lm = self._smooth
        t1 = time.perf_counter()
        out = self.rig.render(cam_bgr, lm, self.settings, self.assets)
        self.last_track_ms = (t1 - t0) * 1000
        self.last_render_ms = (time.perf_counter() - t1) * 1000
        return out

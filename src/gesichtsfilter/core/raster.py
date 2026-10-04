"""Bild-Grundoperationen: Sprites (PNG mit Alpha) und affines Einblenden.

Alle Bilder liegen intern als *vormultipliziertes* BGRA (uint8) vor. Das
vermeidet dunkle Raender beim Skalieren/Drehen, genau wie ein Browser-Canvas.
"""
from pathlib import Path

import cv2
import numpy as np

from ..config import MAX_IMAGE_SIDE


def premultiply(bgra: np.ndarray) -> np.ndarray:
    """Gerades BGRA -> vormultipliziertes BGRA (uint8)."""
    a = bgra[..., 3:4].astype(np.uint16)
    out = bgra.copy()
    out[..., :3] = ((bgra[..., :3].astype(np.uint16) * a + 127) // 255).astype(np.uint8)
    return out


def unpremultiply(pm: np.ndarray) -> np.ndarray:
    """Vormultipliziertes BGRA -> gerades BGRA (fuer PNG-Export)."""
    a = pm[..., 3:4].astype(np.float32)
    out = pm.copy()
    rgb = pm[..., :3].astype(np.float32) * 255.0 / np.maximum(a, 1.0)
    out[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    return out


class Sprite:
    """Ein PNG/Bild mit Alpha, vormultipliziert."""

    def __init__(self, pm: np.ndarray):
        assert pm.ndim == 3 and pm.shape[2] == 4 and pm.dtype == np.uint8
        self.pm = np.ascontiguousarray(pm)

    @property
    def w(self) -> int:
        return self.pm.shape[1]

    @property
    def h(self) -> int:
        return self.pm.shape[0]

    def to_straight_bgra(self) -> np.ndarray:
        return unpremultiply(self.pm)

    def save_png(self, path) -> None:
        """Schreibt das Bild als PNG (auch bei Umlauten im Pfad)."""
        ok, buf = cv2.imencode(".png", self.to_straight_bgra())
        if not ok:
            raise ValueError("PNG konnte nicht erzeugt werden.")
        buf.tofile(str(path))

    @classmethod
    def from_straight_bgra(cls, bgra: np.ndarray) -> "Sprite":
        return cls(premultiply(bgra))

    @classmethod
    def from_file(cls, path, max_side: int = MAX_IMAGE_SIDE) -> "Sprite":
        """Laedt eine Bilddatei (auch mit Umlauten im Pfad)."""
        try:
            data = np.fromfile(str(Path(path)), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        except OSError as e:
            raise ValueError(f"Datei konnte nicht gelesen werden: {e}") from e
        if img is None:
            raise ValueError("Das ist kein lesbares Bild.")
        if img.dtype != np.uint8:  # 16-Bit-PNGs
            img = (img / 257.0).clip(0, 255).astype(np.uint8)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        sp = cls.from_straight_bgra(img)
        return sp.limited(max_side)

    def limited(self, max_side: int) -> "Sprite":
        """Verkleinert (im vormultiplizierten Raum), falls zu gross."""
        m = max(self.w, self.h)
        if m <= max_side:
            return self
        f = max_side / m
        pm = cv2.resize(self.pm, (max(1, round(self.w * f)), max(1, round(self.h * f))),
                        interpolation=cv2.INTER_AREA)
        return Sprite(pm)


def draw_affine(dst: np.ndarray, pm: np.ndarray, m3: np.ndarray) -> None:
    """Blendet ein vormultipliziertes BGRA-Bild mit Transformation m3 (3x3,
    Quell-Pixel -> Ziel-Pixel) per "over" in dst (BGR, uint8) ein.

    Gerechnet wird nur im umschliessenden Rechteck (schnell).
    """
    H, W = dst.shape[:2]
    h, w = pm.shape[:2]
    corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64).T
    t = (m3 @ corners)[:2]
    bx0 = max(int(np.floor(t[0].min())), 0)
    by0 = max(int(np.floor(t[1].min())), 0)
    bx1 = min(int(np.ceil(t[0].max())), W)
    by1 = min(int(np.ceil(t[1].max())), H)
    if bx1 <= bx0 or by1 <= by0:
        return
    m2 = m3[:2].copy()
    m2[0, 2] -= bx0
    m2[1, 2] -= by0
    warped = cv2.warpAffine(pm, m2, (bx1 - bx0, by1 - by0), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    a = warped[..., 3:4].astype(np.uint16)
    roi = dst[by0:by1, bx0:bx1]
    res = warped[..., :3].astype(np.uint16) + (roi.astype(np.uint16) * (255 - a) + 127) // 255
    roi[:] = np.minimum(res, 255).astype(np.uint8)

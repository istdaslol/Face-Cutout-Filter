"""Synthetische Landmarks (478 Punkte) fuer Tests ohne Kamera/Modell."""
import numpy as np

from gesichtsfilter import config as C


def _ring(idx, center, rx, ry, out):
    for k, i in enumerate(idx):
        t = 2 * np.pi * k / len(idx)
        out[i] = (center[0] + rx * np.cos(t), center[1] + ry * np.sin(t))


def make_face(cx=0.5, cy=0.4, roll=0.0, scale=1.0, aspect=16 / 9):
    """Erzeugt Landmarks (normalisiert, UNGESPIEGELT).

    cx, cy = Augenmitte, roll = Neigung (rad), scale = Groesse.
    aspect = Breite/Hoehe des Bildes, damit Kreise rund bleiben.
    """
    rng = np.random.default_rng(0)
    pts = np.tile([cx, cy], (478, 1)).astype(np.float64)
    pts += rng.normal(0, 0.01, pts.shape)           # Reste verstreut
    sx = 0.06 * scale / aspect                       # halbe Augendistanz in x
    sy = 0.06 * scale

    def place(local):                                # lokal (in sy-Einheiten) -> Bild
        c, s = np.cos(roll), np.sin(roll)
        x = local[0] * c - local[1] * s
        y = local[0] * s + local[1] * c
        return (cx + x * sy / aspect, cy + y * sy)

    _ring(C.EYE_A, place((-1.0, 0.0)), 0.30 * sx, 0.14 * sy, pts)
    _ring(C.EYE_B, place((1.0, 0.0)), 0.30 * sx, 0.14 * sy, pts)
    _ring(C.BROW_A, place((-1.0, -0.55)), 0.35 * sx, 0.06 * sy, pts)
    _ring(C.BROW_B, place((1.0, -0.55)), 0.35 * sx, 0.06 * sy, pts)
    _ring(C.LIPS, place((0.0, 2.2)), 0.70 * sx, 0.28 * sy, pts)
    # Punkte ausserhalb der Ringe angleichen (Ringe wurden mit pts-Index geschrieben)
    return pts.astype(np.float32)

"""Ausschnitt (Augen/Mund) mit weicher Kante - Port von cut()/stamp()."""
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import MAX_PATCH
from .geometry import convex_hull, mean_pt, mat_translate, mat_rotate, mat_scale
from .raster import draw_affine

_SHIFT = 4  # Subpixel-Genauigkeit beim Polygon-Fuellen


@dataclass
class Patch:
    """Ausgeschnittenes Stueck Kamerabild (vormultipliziertes BGRA)."""
    pm: np.ndarray
    cx: float   # Bezugspunkt (Mittelwert der Huelle) im Patch
    cy: float


def cut(frame_bgr: np.ndarray, pts, grow: float, feather: float) -> Patch:
    """Schneidet die konvexe Huelle von pts (Pixel) aus dem Kamerabild aus.

    grow    = Vergroesserung der Huelle um ihren Mittelpunkt ("Ausschnitt-Rand")
    feather = Gauss-Weichzeichnung der Maske in Pixeln ("Weiche Kante")
    Logik (Rand m, Boxgroesse, Obergrenze 700) wie in der HTML-Datei.
    """
    hl = convex_hull(pts)
    c = mean_pt(hl)
    g = c + (hl - c) * grow
    m = feather * 2 + 2
    x0 = int(np.floor(g[:, 0].min() - m))
    y0 = int(np.floor(g[:, 1].min() - m))
    x1, y1 = g[:, 0].max(), g[:, 1].max()
    w = int(min(MAX_PATCH, np.ceil(x1 - x0 + m)))
    h = int(min(MAX_PATCH, np.ceil(y1 - y0 + m)))
    w, h = max(w, 1), max(h, 1)

    # Maske: weisses Polygon, danach weichzeichnen
    mask = np.zeros((h, w), np.uint8)
    poly = np.round((g - [x0, y0]) * (1 << _SHIFT)).astype(np.int32)
    cv2.fillPoly(mask, [poly], 255, lineType=cv2.LINE_AA, shift=_SHIFT)
    if feather > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=float(feather),
                                borderType=cv2.BORDER_CONSTANT)

    # Kamerabild-Ausschnitt; ausserhalb des Bildes transparent (wie Canvas)
    H, W = frame_bgr.shape[:2]
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x0 + w, W), min(y0 + h, H)
    color = np.zeros((h, w, 3), np.uint8)
    valid = np.zeros((h, w), np.uint8)
    if sx1 > sx0 and sy1 > sy0:
        color[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = frame_bgr[sy0:sy1, sx0:sx1]
        valid[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = 255
    alpha = ((mask.astype(np.uint16) * valid + 127) // 255).astype(np.uint8)
    pm = np.empty((h, w, 4), np.uint8)
    pm[..., :3] = ((color.astype(np.uint16) * alpha[..., None] + 127) // 255).astype(np.uint8)
    pm[..., 3] = alpha
    return Patch(pm, float(c[0] - x0), float(c[1] - y0))


def stamp(dst: np.ndarray, patch: Patch, x: float, y: float, scale: float, rot: float) -> None:
    """Setzt den Patch mit seinem Bezugspunkt auf (x, y), skaliert und gedreht."""
    m = (mat_translate(x, y) @ mat_rotate(rot) @ mat_scale(scale)
         @ mat_translate(-patch.cx, -patch.cy))
    draw_affine(dst, patch.pm, m)

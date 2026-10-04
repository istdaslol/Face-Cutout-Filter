"""Demo-Bild und Erdnuss, per OpenCV gezeichnet (Port von demo()/peanut())."""
import cv2
import numpy as np

from .. import config as C
from .raster import Sprite, premultiply
from .settings import RigAssets

_SS = 2  # Zeichnen in doppelter Aufloesung, dann verkleinern (Kantenglaettung)


def _bgra(hexcol: str):
    b, g, r = C.hex_to_bgr(hexcol)
    return (b, g, r, 255)


def _rounded_rect_poly(x, y, w, h, r, n=24):
    r = min(r, w / 2, h / 2)
    pts = []
    for cx, cy, a0 in [(x + w - r, y + r, -90), (x + w - r, y + h - r, 0),
                       (x + r, y + h - r, 90), (x + r, y + r, 180)]:
        for t in np.linspace(a0, a0 + 90, n):
            pts.append((cx + r * np.cos(np.radians(t)), cy + r * np.sin(np.radians(t))))
    return np.round(np.array(pts) * _SS).astype(np.int32)


def _downscale(canvas_straight: np.ndarray) -> Sprite:
    """2x-Zeichnung -> Sprite (im vormultiplizierten Raum verkleinert)."""
    pm = premultiply(canvas_straight)
    h, w = pm.shape[0] // _SS, pm.shape[1] // _SS
    return Sprite(cv2.resize(pm, (w, h), interpolation=cv2.INTER_AREA))


def _bezier(p0, p1, p2, n=20):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2 = map(np.array, (p0, p1, p2))
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def demo_canvas() -> Sprite:
    """Glatzkoepfiges Gesicht ohne Ohren + Shirt. Groesse 600 x (470+SHIRT_HOEHE)."""
    h = 470 + C.SHIRT_HOEHE
    cv = np.zeros((h * _SS, 600 * _SS, 4), np.uint8)
    lw = 10 * _SS
    skin, line, shirt = _bgra(C.HAUTFARBE), _bgra(C.KONTUR), _bgra(C.SHIRT)

    def S(v):
        return int(round(v * _SS))

    # Shirt (abgerundetes Rechteck: Fuellung + Kontur)
    poly = _rounded_rect_poly((600 - C.SHIRT_BREITE) / 2, 470, C.SHIRT_BREITE,
                              C.SHIRT_HOEHE + 40, C.SHIRT_RUNDUNG)
    cv2.fillPoly(cv, [poly], shirt)
    cv2.polylines(cv, [poly], True, line, lw)
    # Hals
    cv2.rectangle(cv, (S(262), S(370)), (S(338), S(470)), skin, -1)
    cv2.rectangle(cv, (S(262), S(370)), (S(338), S(470)), line, lw)
    # Kopf
    cv2.ellipse(cv, (S(300), S(230)), (S(142), S(176)), 0, 0, 360, skin, -1)
    cv2.ellipse(cv, (S(300), S(230)), (S(142), S(176)), 0, 0, 360, line, lw)
    # Nase (zwei quadratische Kurven, runde Enden)
    nose = np.vstack([_bezier((300, 225), (288, 265), (300, 278)),
                      _bezier((300, 278), (312, 282), (322, 276))])
    nz = np.round(nose * _SS).astype(np.int32)
    cv2.polylines(cv, [nz], False, line, lw)
    for p in (nz[0], nz[-1]):
        cv2.circle(cv, tuple(int(v) for v in p), lw // 2, line, -1)
    return _downscale(cv)


def _crop(sp: Sprite, y0: int, y1: int) -> Sprite:
    return Sprite(sp.pm[y0:y1].copy())


def demo_assets(two: bool = False) -> RigAssets:
    """Demo-Bild samt Markern (Werte wie loadDemo() in der HTML-Datei)."""
    c = demo_canvas()
    h = c.h
    if not two:
        return RigAssets(
            head=c,
            head_markers=[[.4, 216 / h], [.6, 216 / h], [.5, 320 / h], [.5, 380 / h], [.5, 472 / h]])
    body = _crop(c, 430, h)
    return RigAssets(
        head=_crop(c, 0, 470),
        head_markers=[[.4, .457], [.6, .457], [.5, .67], [.5, .9], [.5, .968]],
        body=body,
        body_marker=[[.5, 25 / (h - 430)]])


def peanut_sprite(seed: int = 1) -> Sprite:
    """Die urspruengliche Erdnuss (zwei Kreise), 600 x 800, transparent."""
    rng = np.random.default_rng(seed)
    cv = np.zeros((800 * _SS, 600 * _SS, 4), np.uint8)
    parts = [(300, 230, 170), (300, 540, 210)]
    for x, y, r in parts:
        cv2.circle(cv, (x * _SS, y * _SS), (r + 12) * _SS, (0x23, 0x44, 0x6b, 255), -1)
    for x, y, r in parts:
        cv2.circle(cv, (x * _SS, y * _SS), r * _SS, (0x64, 0xa8, 0xd9, 255), -1)
    for i in range(90):
        t = rng.random() * 6.28
        rr = np.sqrt(rng.random())
        x, y, r = parts[i % 2]
        cv2.circle(cv, (int((x + np.cos(t) * rr * r * .9) * _SS), int((y + np.sin(t) * rr * r * .9) * _SS)),
                   int((3 + rng.random() * 3) * _SS), (0x4a, 0x86, 0xb8, 255), -1)
    return _downscale(cv)


def peanut_assets() -> RigAssets:
    return RigAssets(head=peanut_sprite(), head_markers=[m[:] for m in C.PEANUT_MARKERS])

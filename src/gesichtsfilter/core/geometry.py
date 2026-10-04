"""Kleine geometrische Helfer (Port von hull/mean/clamp aus der HTML-Datei)."""
import numpy as np


def clamp(x, a, b):
    return max(a, min(b, x))


def mean_pt(pts) -> np.ndarray:
    """Mittelwert aller Punkte (wie mean() in der HTML-Datei)."""
    return np.asarray(pts, dtype=np.float64).mean(axis=0)


def convex_hull(points) -> np.ndarray:
    """Konvexe Huelle (Monotone Chain), exakt wie hull() in der HTML-Datei.

    Kollineare Punkte werden entfernt (cross <= 0 wird verworfen).
    """
    p = sorted((float(x), float(y)) for x, y in points)

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for q in p:
        while len(lo) > 1 and cr(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(up) > 1 and cr(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return np.array(lo[:-1] + up[:-1], dtype=np.float64)


def mat_translate(tx, ty) -> np.ndarray:
    return np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], dtype=np.float64)


def mat_scale(s) -> np.ndarray:
    return np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float64)


def mat_rotate(r) -> np.ndarray:
    """Wie ctx.rotate(r): positiver Winkel dreht im Uhrzeigersinn (y nach unten)."""
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)

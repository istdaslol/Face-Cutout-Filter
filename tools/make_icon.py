"""Erzeugt assets/app.ico und assets/app.png (gezeichnet mit OpenCV, ohne weitere Abhaengigkeiten).

Das Ergebnis ist eingecheckt; das Skript wird nur gebraucht, wenn das Icon geaendert werden soll.
Aufruf:  python tools/make_icon.py
"""
import struct
import sys
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "assets"
SIZES_BMP = (16, 24, 32, 48, 64, 128)   # klassische DIB-Eintraege (maximal kompatibel)
SIZE_PNG = 256                           # 256 px als PNG-Eintrag (wie von Windows ueblich)
BG, SKIN, LINE, MOUTH = (0x47, 0xB3, 0xFF), (0xB0, 0xCF, 0xF1), (0x6A, 0x8E, 0xB9), (0x4A, 0x4A, 0xD0)   # BGR


def master(n: int = 1024) -> np.ndarray:
    """Zeichnet das Icon in n x n als vormultipliziertes BGRA (float32 0..1)."""
    s = n / 1024
    P = lambda v: int(round(v * s))   # noqa: E731
    color = np.zeros((n, n, 3), np.uint8)
    color[:] = BG
    cx = P(512)
    cv2.ellipse(color, (cx, P(560)), (P(300), P(370)), 0, 0, 360, SKIN, -1, cv2.LINE_AA)
    cv2.ellipse(color, (cx, P(560)), (P(300), P(370)), 0, 0, 360, LINE, P(26), cv2.LINE_AA)
    for dx in (-130, 130):                                    # Augen
        cv2.ellipse(color, (cx + P(dx), P(500)), (P(78), P(52)), 0, 0, 360, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(color, (cx + P(dx), P(500)), P(34), (40, 25, 15), -1, cv2.LINE_AA)
        cv2.ellipse(color, (cx + P(dx), P(395)), (P(80), P(14)), 0, 0, 360, (40, 40, 40), -1, cv2.LINE_AA)   # Braue
    cv2.ellipse(color, (cx, P(740)), (P(120), P(56)), 0, 0, 360, MOUTH, -1, cv2.LINE_AA)
    alpha = np.zeros((n, n), np.uint8)                        # Hintergrund: abgerundetes Quadrat
    r, m = P(230), P(24)
    cv2.rectangle(alpha, (m + r, m), (n - m - r, n - m), 255, -1)
    cv2.rectangle(alpha, (m, m + r), (n - m, n - m - r), 255, -1)
    for x, y in ((m + r, m + r), (n - m - r, m + r), (m + r, n - m - r), (n - m - r, n - m - r)):
        cv2.circle(alpha, (x, y), r, 255, -1, cv2.LINE_AA)
    a = alpha.astype(np.float32)[..., None] / 255
    return np.concatenate([color.astype(np.float32) / 255 * a, a], axis=2)


def at_size(pm: np.ndarray, n: int) -> np.ndarray:
    """Verkleinert (im vormultiplizierten Raum) und liefert gerades BGRA uint8."""
    small = cv2.resize(pm, (n, n), interpolation=cv2.INTER_AREA)
    a = small[..., 3:4]
    rgb = np.where(a > 0, small[..., :3] / np.maximum(a, 1e-6), 0)
    return np.clip(np.concatenate([rgb, a], axis=2) * 255 + 0.5, 0, 255).astype(np.uint8)


def dib(img: np.ndarray) -> bytes:
    h, w = img.shape[:2]
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)               # AND-Maske: leer, Transparenz kommt aus Alpha
    head = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, w * h * 4 + len(mask), 0, 0, 0, 0)
    return head + np.ascontiguousarray(img[::-1]).tobytes() + mask


def build_ico(images) -> bytes:
    """images: Liste (Groesse, Bytes) - fertige Eintragsdaten (DIB oder PNG)."""
    out, data, offset = [struct.pack("<HHH", 0, 1, len(images))], [], 6 + 16 * len(images)
    for size, blob in images:
        out.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset))
        data.append(blob)
        offset += len(blob)
    return b"".join(out + data)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    pm = master()
    entries = [(n, dib(at_size(pm, n))) for n in SIZES_BMP]
    big = at_size(pm, SIZE_PNG)
    ok, png = cv2.imencode(".png", big)
    assert ok
    entries.append((SIZE_PNG, png.tobytes()))
    (OUT / "app.ico").write_bytes(build_ico(entries))
    (OUT / "app.png").write_bytes(png.tobytes())
    print(f"geschrieben: {OUT / 'app.ico'} ({len(entries)} Groessen), {OUT / 'app.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

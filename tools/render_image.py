"""Schnelltest: ein Foto durch den kompletten Kern schicken (ohne UI/Kamera).

Beispiele:
  python tools/render_image.py foto.jpg
  python tools/render_image.py foto.jpg --modus 2 --groesse 0.6 --hintergrund "#00ff00"
  python tools/render_image.py foto.jpg --bild meinkopf.png --marker 0.4,0.3 0.6,0.3 0.5,0.55 0.5,0.7 0.5,0.9

Das Ergebnis landet in <Projekt>/ausgabe/<foto>_ausgabe.png (oder --ziel).
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gesichtsfilter.core.demo import demo_assets, peanut_assets  # noqa: E402
from gesichtsfilter.core.pipeline import Pipeline  # noqa: E402
from gesichtsfilter.core.raster import Sprite  # noqa: E402
from gesichtsfilter.core.settings import RigAssets, Settings  # noqa: E402
from gesichtsfilter.core.tracker import FaceTracker  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("foto")
    ap.add_argument("--modus", type=int, default=1, choices=[0, 1, 2])
    ap.add_argument("--quelle", default="demo", choices=["demo", "erdnuss"])
    ap.add_argument("--bild", help="eigenes Kopf-PNG (statt Demo/Erdnuss)")
    ap.add_argument("--marker", nargs="+", help="Marker als x,y (3 oder 5 Stueck, relativ 0..1)")
    ap.add_argument("--groesse", type=float, default=1.0)
    ap.add_argument("--hintergrund", default="cam")
    ap.add_argument("--kein-spiegeln", action="store_true")
    ap.add_argument("--ziel", help="Ausgabedatei (Standard: ausgabe/<foto>_ausgabe.png im Projekt)")
    a = ap.parse_args()

    img = cv2.imdecode(np.fromfile(a.foto, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        sys.exit("Foto nicht lesbar.")
    if a.bild:
        assets = RigAssets(head=Sprite.from_file(a.bild))
        if a.marker:
            m = [[float(v) for v in p.split(",")] for p in a.marker]
            assets.head_markers[:len(m)] = m
    elif a.quelle == "erdnuss":
        assets = peanut_assets()
    else:
        assets = demo_assets(two=(a.modus == 2))

    tracker = FaceTracker()
    print("Tracking-Delegate:", tracker.delegate_used)
    pipe = Pipeline(tracker, Settings(mode=a.modus, image_scale=a.groesse,
                                      background=a.hintergrund, mirror=not a.kein_spiegeln), assets)
    pipe.rig.set_rest_pose()
    out = pipe.process(img)
    if a.ziel:
        ziel = Path(a.ziel)
    else:  # absichtlich NICHT neben dem Foto, damit Tests es nicht als Eingabe verwenden
        ziel = Path(__file__).resolve().parent.parent / "ausgabe" / (Path(a.foto).stem + "_ausgabe.png")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", out)[1].tofile(str(ziel))
    print("Geschrieben:", ziel)


if __name__ == "__main__":
    main()

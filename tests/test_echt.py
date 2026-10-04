"""Tests mit ECHTEM MediaPipe-Modell und Beispielbildern aus tests/bilder/.

Werden uebersprungen, wenn Modell oder Bilder fehlen. Ergebnisbilder landen in
tests/ausgabe/ und koennen mit dem Auge geprueft werden.

Namenskonvention: Bilder, die KEIN Gesicht enthalten, beginnen mit "kein_gesicht".
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from gesichtsfilter import config as C
from gesichtsfilter.core.demo import demo_assets, peanut_assets
from gesichtsfilter.core.pipeline import Pipeline
from gesichtsfilter.core.settings import Settings
from gesichtsfilter.paths import MODEL_REL, resource

# Dateien mit "_ausgabe" im Namen sind Ergebnisse von tools/render_image.py, keine Eingaben
BILDER = sorted(p for p in (Path(__file__).parent / "bilder").glob("*")
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
                and "_ausgabe" not in p.stem.lower())
AUSGABE = Path(__file__).parent / "ausgabe"

pytestmark = pytest.mark.skipif(
    not resource(MODEL_REL).exists() or not BILDER,
    reason="Modell (tools/fetch_model.py) oder Bilder in tests/bilder/ fehlen")


@pytest.fixture(scope="module")
def tracker():
    from gesichtsfilter.core.tracker import FaceTracker
    t = FaceTracker(use_gpu=False)
    yield t
    t.close()


def lade(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.parametrize("pfad", BILDER, ids=lambda p: p.name)
def test_tracking_und_geometrie(tracker, pfad):
    img = lade(pfad)
    assert img is not None
    lm = tracker.detect(img)
    if pfad.name.startswith("kein_gesicht"):
        assert lm is None
        return
    assert lm is not None, "Kein Gesicht erkannt"
    assert lm.shape == (478, 2) or lm.shape[0] >= 468
    assert lm.min() > -0.2 and lm.max() < 1.2
    ea, eb = lm[C.EYE_A].mean(0), lm[C.EYE_B].mean(0)
    assert ea[0] < eb[0], "Auge A muss im ungespiegelten Bild links liegen"
    assert eb[0] - ea[0] > 0.02
    mund = lm[C.LIPS].mean(0)
    assert mund[1] > (ea[1] + eb[1]) / 2, "Mund muss unter den Augen liegen"


@pytest.mark.parametrize("pfad", [p for p in BILDER if not p.name.startswith("kein_gesicht")][:6],
                         ids=lambda p: p.name)
def test_verkleinertes_tracking_ist_konsistent(pfad):
    from gesichtsfilter.core.tracker import FaceTracker
    img = lade(pfad)
    klein, gross = FaceTracker(track_size=(640, 360)), FaceTracker(track_size=(4000, 4000))
    try:
        a, b = klein.detect(img), gross.detect(img)
    finally:
        klein.close(); gross.close()
    assert a is not None and b is not None
    assert np.abs(a - b).mean() < 0.02


@pytest.mark.parametrize("pfad", [p for p in BILDER if not p.name.startswith("kein_gesicht")],
                         ids=lambda p: p.name)
@pytest.mark.parametrize("modus", [0, 1, 2])
def test_render_alle_modi(tracker, pfad, modus):
    img = lade(pfad)
    assets = demo_assets(two=(modus == 2)) if modus != 1 else peanut_assets()
    pipe = Pipeline(tracker, Settings(mode=modus, image_scale=0.6 if modus == 2 else 1.0), assets)
    pipe.rig.set_rest_pose()
    out = pipe.process(img)
    assert out.shape == img.shape and out.dtype == np.uint8
    assert not np.array_equal(out, cv2.flip(img, 1)), "Es wurde nichts eingeblendet"
    AUSGABE.mkdir(exist_ok=True)
    cv2.imwrite(str(AUSGABE / f"{pfad.stem}_modus{modus}.png"), out)

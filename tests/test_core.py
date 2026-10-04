"""Tests der Kernlogik ohne Kamera und ohne MediaPipe-Modell."""
import math

import numpy as np
import pytest

from fake_face import make_face
from gesichtsfilter import config as C
from gesichtsfilter.core.cutout import cut
from gesichtsfilter.core.demo import demo_assets, peanut_assets
from gesichtsfilter.core.geometry import convex_hull, mean_pt, mat_rotate, mat_translate
from gesichtsfilter.core.pipeline import Pipeline
from gesichtsfilter.core.raster import Sprite, draw_affine
from gesichtsfilter.core.rig import Rig
from gesichtsfilter.core.settings import RigAssets, Settings

W, H = 1280, 720
GREEN = (0, 255, 0)


def cam(color=GREEN):
    f = np.empty((H, W, 3), np.uint8)
    f[:] = color
    return f


# ---------------------------------------------------------------- Konstanten
def test_landmark_indizes_gueltig():
    for lst in (C.EYE_A, C.EYE_B, C.BROW_A, C.BROW_B, C.LIPS):
        assert len(set(lst)) == len(lst)
        assert all(0 <= i < 468 for i in lst)
    assert (len(C.EYE_A), len(C.BROW_A), len(C.LIPS)) == (16, 10, 20)
    assert not set(C.EYE_A) & set(C.EYE_B)


# ---------------------------------------------------------------- Geometrie
def test_hull_entfernt_innere_und_kollineare_punkte():
    pts = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 5), (5, 0), (2, 3)]
    h = convex_hull(pts)
    assert {tuple(p) for p in h} == {(0, 0), (10, 0), (10, 10), (0, 10)}
    assert np.allclose(mean_pt(h), (5, 5))


# ---------------------------------------------------------------- Ausschnitt
def test_cut_groesse_mitte_und_weiche_kante():
    pts = [(100, 100), (200, 100), (200, 160), (100, 160)]
    hard = cut(cam(), pts, 1.0, 0)
    soft = cut(cam(), pts, 1.0, 8)
    # Box: Breite = 100 + 2*m, mit m = feather*2+2 (HTML-Logik)
    assert hard.pm.shape[1] == 100 + 2 * 2 and soft.pm.shape[1] == 100 + 2 * 18
    assert soft.pm.shape[0] > hard.pm.shape[0]
    # Bezugspunkt = Mitte der Huelle: x0 = 100-18 -> cx = 150-82
    assert abs(soft.cx - (150 - (100 - 18))) < 1.0
    # Mitte voll deckend, Rand der Box transparent, harte Kante schaerfer
    cy, cx = int(soft.cy), int(soft.cx)
    assert soft.pm[cy, cx, 3] == 255
    assert soft.pm[0, 0, 3] == 0
    assert hard.pm[:, :, 3].max() == 255
    edge_soft = (soft.pm[cy, :, 3].astype(int)[1:] - soft.pm[cy, :, 3].astype(int)[:-1]).max()
    edge_hard = (hard.pm[int(hard.cy), :, 3].astype(int)[1:] - hard.pm[int(hard.cy), :, 3].astype(int)[:-1]).max()
    assert edge_soft < edge_hard


def test_cut_vormultipliziert_und_ausserhalb_des_bildes():
    # teilweise ausserhalb: kein Absturz, ausserhalb transparent
    pts = [(-30, 100), (20, 100), (20, 140), (-30, 140)]
    p = cut(cam(), pts, 1.0, 6)
    assert p.pm.shape[0] <= C.MAX_PATCH and p.pm.shape[1] <= C.MAX_PATCH
    assert (p.pm[..., :3] <= p.pm[..., 3:4]).all()          # vormultipliziert
    # ganz ausserhalb
    p2 = cut(cam(), [(-500, -500), (-400, -500), (-400, -400)], 1.0, 4)
    assert p2.pm[..., 3].max() == 0


def test_cut_obergrenze_700():
    p = cut(cam(), [(0, 0), (1200, 0), (1200, 700), (0, 700)], 1.2, 8)
    assert max(p.pm.shape[:2]) <= C.MAX_PATCH


# ---------------------------------------------------------------- Raster
def test_draw_affine_identitaet_und_drehung():
    pm = np.zeros((10, 10, 4), np.uint8)
    pm[..., :] = (0, 0, 255, 255)                           # rot, deckend
    dst = np.zeros((50, 50, 3), np.uint8)
    draw_affine(dst, pm, mat_translate(20, 20))
    assert tuple(dst[25, 25]) == (0, 0, 255) and tuple(dst[15, 15]) == (0, 0, 0)
    dst2 = np.zeros((50, 50, 3), np.uint8)
    draw_affine(dst2, pm, mat_translate(25, 25) @ mat_rotate(math.pi / 4) @ mat_translate(-5, -5))
    assert dst2[25, 25, 2] == 255 and dst2[25, 25 + 8, 2] == 0   # Raute


def test_draw_affine_halbtransparent_mischt():
    pm = np.zeros((4, 4, 4), np.uint8)
    pm[..., :] = (0, 0, 128, 128)                           # 50% rot, vormultipliziert
    dst = np.full((10, 10, 3), 200, np.uint8)
    draw_affine(dst, pm, mat_translate(3, 3))
    assert abs(int(dst[4, 4, 2]) - 228) <= 2 and abs(int(dst[4, 4, 0]) - 100) <= 2


# ---------------------------------------------------------------- Rig
def head_sprite(color, w, h):
    px = np.zeros((h, w, 4), np.uint8)
    px[...] = (*color, 255)
    return Sprite.from_straight_bgra(px)


def synth_assets():
    return RigAssets(head=head_sprite((0, 0, 255), 200, 300),
                     head_markers=[[.35, .3], [.65, .3], [.5, .5], [.5, .7], [.5, .9]],
                     body=head_sprite((255, 0, 0), 300, 200), body_marker=[[.5, .1]])


def is_green(px):
    return px[1] > 200 and px[0] < 60 and px[2] < 60


def expected_marker_px(a, m, s0, x0, y0, iw, ih):
    return x0 + a[m][0] * iw * s0, y0 + a[m][1] * ih * s0


def test_modus1_augen_landen_auf_markern_in_ruhelage():
    s = Settings(mode=1, background="#000000", mirror=False)
    assets = synth_assets()
    rig = Rig()
    rig.set_rest_pose()
    lm = make_face(0.5, 0.4)
    out = rig.render(cam(), lm, s, assets)
    ih, iw = 300, 200
    s0 = s.image_scale * H * .85 / ih
    x0, y0 = (W - iw * s0) / 2, H - ih * s0
    for m in (0, 1, 2):
        x, y = expected_marker_px(assets.head_markers, m, s0, x0, y0, iw, ih)
        assert is_green(out[int(round(y)), int(round(x))]), f"Marker {m} nicht gruen"
    # Kopf selbst ist rot, Bereich ausserhalb schwarz
    assert out[int(y0 + 5 * s0), int(W / 2)][2] > 200
    assert tuple(out[5, 5]) == (0, 0, 0)


def test_modus1_kopf_folgt_koerper_bleibt():
    s = Settings(mode=1, background="#000000", mirror=False)
    assets = synth_assets()
    rig = Rig()
    rig.set_rest_pose()
    a = rig.render(cam(), make_face(0.5, 0.4), s, assets)
    b = rig.render(cam(), make_face(0.5, 0.4), s, assets)
    assert np.array_equal(a, b)
    moved = rig.render(cam(), make_face(0.58, 0.46), s, assets)      # Kopf bewegt
    ih = 300
    s0 = H * .85 / ih
    y0 = H - ih * s0
    yb = int(y0 + .9 * ih * s0)
    # unter dem Hals-Pivot (Koerper) unveraendert
    assert np.array_equal(a[yb + 8:], moved[yb + 8:])
    # Kopf-Bereich ist anders
    assert not np.array_equal(a[:yb - 10], moved[:yb - 10])
    # Gruene Augen sind um dx verschoben (0.08*1280 = 102 px)
    gx_a = np.where(a[..., 1] > 200)[1].mean()
    gx_m = np.where(moved[..., 1] > 200)[1].mean()
    assert abs((gx_m - gx_a) - 0.08 * W) < 8


def test_modus1_follow_null_bewegt_nichts():
    s = Settings(mode=1, follow=0.0, background="#000000", mirror=False)
    assets = synth_assets()
    rig = Rig()
    rig.set_rest_pose()
    a = rig.render(cam(), make_face(0.5, 0.4), s, assets)
    m = rig.render(cam(), make_face(0.6, 0.5, roll=0.2), s, assets)
    s0 = H * .85 / 300
    y0 = H - 300 * s0
    # Oberer Kopfbereich (ohne Augen/Mund) und Koerper: pixelgleich
    top = slice(int(y0) + 2, int(y0 + .2 * 300 * s0))
    assert np.array_equal(a[top], m[top])
    assert np.array_equal(a[int(y0 + .95 * 300 * s0):], m[int(y0 + .95 * 300 * s0):])


def test_modus1_drehung_und_zoom_werden_begrenzt():
    s = Settings(mode=1, follow=1.5, background="#000000", mirror=False)
    rig = Rig()
    rig.set_rest_pose()
    rig.render(cam(), make_face(0.5, 0.4), s, synth_assets())
    out = rig.render(cam(), make_face(0.5, 0.4, roll=1.2, scale=3.0), s, synth_assets())
    assert out.shape == (H, W, 3)                             # kein Absturz bei Extremwerten


def test_modus0_bild_folgt_dem_gesicht_starr():
    s = Settings(mode=0, background="#000000", mirror=False)
    assets = synth_assets()
    out = Rig().render(cam(), make_face(0.5, 0.4), s, assets)
    # Marker "Auge links" liegt bei Augenmitte-links => gruener Fleck dort
    face = make_face(0.5, 0.4)
    ex = float(np.mean(face[C.EYE_A, 0]) * W)
    ey = float(np.mean(face[C.EYE_A, 1]) * H)
    # Eyes sind in Modus 0 auf Marker platziert, die relativ zur Augenmitte liegen
    assert out[int(ey), int(ex)].tolist() != [0, 0, 0]
    # Mit Kopfbewegung wandert das ganze Bild mit
    out2 = Rig().render(cam(), make_face(0.4, 0.5), s, assets)
    red1 = np.where((out[..., 2] > 200) & (out[..., 1] < 50))
    red2 = np.where((out2[..., 2] > 200) & (out2[..., 1] < 50))
    assert abs((red2[1].mean() - red1[1].mean()) - (-0.1 * W)) < 10
    assert abs((red2[0].mean() - red1[0].mean()) - (0.1 * H)) < 10


def test_modus2_kopf_hinter_koerper():
    assets = synth_assets()
    base = dict(mode=2, background="#000000", mirror=False, head_ratio=1.0)
    for behind, expect in ((False, "rot"), (True, "blau")):
        rig = Rig()
        rig.set_rest_pose()
        out = rig.render(cam(), make_face(0.5, 0.4), Settings(behind=behind, **base), assets)
        # Pivot (Hals unten) liegt am Hals-Anker des Koerpers
        b = assets.body
        sB = 1.0 * H * .5 / b.h
        Nx = W / 2
        Ny = (H - b.h * sB) + .1 * b.h * sB
        px = out[int(Ny) + 2, int(Nx)]
        if expect == "rot":
            assert px[2] > 200 and px[0] < 50
        else:
            assert px[0] > 200 and px[2] < 50


def test_modus2_kopf_zu_koerper_regler_skaliert_kopf():
    assets = synth_assets()
    rig = Rig()
    rig.set_rest_pose()
    a = rig.render(cam(), make_face(), Settings(mode=2, background="#000000", mirror=False, head_ratio=1.0, image_scale=.5), assets)
    rig2 = Rig()
    rig2.set_rest_pose()
    b = rig2.render(cam(), make_face(), Settings(mode=2, background="#000000", mirror=False, head_ratio=2.0, image_scale=.5), assets)
    red = lambda o: ((o[..., 2] > 200) & (o[..., 1] < 50) & (o[..., 0] < 50)).sum()
    assert 3.0 < red(b) / red(a) < 5.0                         # Flaeche ~ 2^2


def test_ohne_gesicht_oder_ohne_bild_nur_hintergrund():
    s = Settings(background="#ff0000", mirror=False)
    out = Rig().render(cam(), None, s, synth_assets())
    assert (out == np.array((0, 0, 255), np.uint8)).all()
    out2 = Rig().render(cam((5, 6, 7)), make_face(), Settings(mirror=False), RigAssets())
    assert (out2 == np.array((5, 6, 7), np.uint8)).all()


def test_spiegeln_dreht_kamerabild():
    f = cam((0, 0, 0))
    f[:, :100] = (255, 255, 255)
    out = Rig().render(f, None, Settings(mirror=True), RigAssets())
    assert out[10, W - 5].tolist() == [255, 255, 255] and out[10, 5].tolist() == [0, 0, 0]


def test_alle_modi_mit_demo_und_erdnuss():
    for mode, assets in ((0, demo_assets(False)), (1, demo_assets(False)),
                         (1, peanut_assets()), (2, demo_assets(True))):
        rig = Rig()
        rig.set_rest_pose()
        out = rig.render(cam(), make_face(), Settings(mode=mode), assets)
        assert out.shape == (H, W, 3) and out.dtype == np.uint8


# ---------------------------------------------------------------- Pipeline
class FakeTracker:
    def __init__(self, seq):
        self.seq, self.calls = list(seq), 0

    def detect(self, bgr):
        r = self.seq[min(self.calls, len(self.seq) - 1)]
        self.calls += 1
        return r


def test_pipeline_glaettung_und_gesichtsverlust():
    tr = FakeTracker([make_face(0.5, 0.4), make_face(0.6, 0.4), None, make_face(0.5, 0.4)])
    p = Pipeline(tr, Settings(mirror=False), synth_assets())
    p.process(cam())
    first = p._smooth.copy()
    p.process(cam())
    # 60% des Sprungs
    assert abs((p._smooth[C.EYE_A[0], 0] - first[C.EYE_A[0], 0]) - 0.6 * 0.1) < 0.01
    p.process(cam())
    assert p._smooth is None                                   # Verlust -> Reset
    p.process(cam())
    assert np.allclose(p._smooth, make_face(0.5, 0.4))         # startet ohne Nachzieher


def test_pipeline_tracking_jeden_zweiten_frame():
    tr = FakeTracker([make_face(0.5, 0.4), make_face(0.52, 0.4), make_face(0.54, 0.4)])
    p = Pipeline(tr, Settings(mirror=False, track_every=2), synth_assets())
    for _ in range(5):
        p.process(cam())
    assert tr.calls == 3                                       # Frames 0, 2, 4
    # Vorhersage: Detektionen bei x=0.5 und 0.6, uebersprungener Frame -> 0.6 + 0.5*0.1 = 0.65
    tr2 = FakeTracker([make_face(0.5, 0.4), make_face(0.6, 0.4)])
    p2 = Pipeline(tr2, Settings(mirror=False, track_every=2), synth_assets())
    for _ in range(3):
        p2.process(cam())                                      # Frame 0 det, 1 skip, 2 det
    t = p2._target(cam())                                      # Frame 3 = uebersprungen
    assert tr2.calls == 2
    assert np.allclose(t[:, 0], make_face(0.5, 0.4)[:, 0] + 0.15, atol=1e-5)


def test_fehlendes_modell_gibt_verstaendliche_meldung(tmp_path):
    from gesichtsfilter.core.tracker import FaceTracker, TrackerError
    with pytest.raises(TrackerError) as e:
        FaceTracker(model_path=tmp_path / "gibt_es_nicht.task")
    assert "fetch_model" in str(e.value)


def test_einstellungen_roundtrip_und_unbekannte_schluessel():
    s = Settings(mode=2, feather=3, background="#000000")
    s2 = Settings.from_dict({**s.to_dict(), "zukunft": 1})
    assert s2 == s


def test_augen_und_mund_ausschnitt_sind_unabhaengig(monkeypatch):
    """eye_margin wirkt nur auf die Augen, mouth_margin nur auf den Mund."""
    from gesichtsfilter.core import rig as rig_mod
    calls = []
    real = rig_mod.cut

    def spy(frame, pts, grow, feather):
        calls.append((len(pts), grow))
        return real(frame, pts, grow, feather)

    monkeypatch.setattr(rig_mod, "cut", spy)
    for mode in (0, 1, 2):
        calls.clear()
        s = Settings(mode=mode, brows=False, eye_margin=1.1, mouth_margin=0.8, mirror=False)
        r = Rig()
        r.set_rest_pose()
        r.render(cam(), make_face(), s, demo_assets(two=(mode == 2)))
        eyes = [g for n, g in calls if n == len(C.EYE_A)]
        mouth = [g for n, g in calls if n == len(C.LIPS)]
        assert eyes == [1.1, 1.1] and mouth == [0.8], f"Modus {mode}: {calls}"


def test_kleinerer_mund_ausschnitt_gibt_kleineren_patch():
    pts = make_face()[C.LIPS] * [W, H]
    gross = cut(cam(), pts, 1.4, 6)
    klein = cut(cam(), pts, 0.8, 6)
    assert klein.pm.shape[1] < gross.pm.shape[1] and klein.pm.shape[0] < gross.pm.shape[0]


def test_altes_profil_mit_margin_wird_umgerechnet():
    s = Settings.from_dict({"margin": 1.3, "feather": 5})
    assert abs(s.eye_margin - 1.3) < 1e-9 and abs(s.mouth_margin - 1.4) < 1e-9 and s.feather == 5
    # neue Schluessel haben Vorrang vor dem alten
    s2 = Settings.from_dict({"margin": 1.3, "eye_margin": 1.0, "mouth_margin": 0.9})
    assert (s2.eye_margin, s2.mouth_margin) == (1.0, 0.9)


# ---------------------------------------------------------------- Kopfverfolgung aus (Modus 0)
def _red(o):
    return (o[..., 2] > 200) & (o[..., 1] < 50) & (o[..., 0] < 50)


def _mode0(track, face, rest_face=None, **kw):
    s = Settings(mode=0, background="#000000", mirror=False, track_head=track, **kw)
    r = Rig()
    r.set_rest_pose()
    r.render(cam(), rest_face if rest_face is not None else face, s, synth_assets())   # Ruhelage
    return r.render(cam(), face, s, synth_assets())


def test_modus0_ohne_kopfverfolgung_bleibt_das_png_stehen():
    rest = make_face(0.5, 0.4)
    for moved in (make_face(0.62, 0.5), make_face(0.5, 0.4, roll=0.35), make_face(0.5, 0.4, scale=1.4),
                  make_face(0.4, 0.35, roll=-0.2, scale=0.8)):
        a = _mode0(False, rest)
        b = _mode0(False, moved, rest_face=rest)
        # PNG-Umriss (ohne die Augen-/Mund-Ausschnitte) ist identisch: Zeilen oberhalb der Augen
        # und unterhalb des Mundes. Aus der Mitte kommen die eingeblendeten Ausschnitte.
        red_a, red_b = _red(a), _red(b)
        ys = np.where(red_a.any(axis=1))[0]
        top = slice(ys[0], ys[0] + (ys[-1] - ys[0]) // 5)
        bottom = slice(ys[0] + (ys[-1] - ys[0]) * 4 // 5, ys[-1] + 1)
        assert np.array_equal(red_a[top], red_b[top]), "oberer PNG-Rand hat sich bewegt"
        assert np.array_equal(red_a[bottom], red_b[bottom]), "unterer PNG-Rand hat sich bewegt"
        assert ys[0] == np.where(red_b.any(axis=1))[0][0]


def test_modus0_mit_kopfverfolgung_bewegt_das_png_weiter():
    rest = make_face(0.5, 0.4)
    a, b = _mode0(True, rest), _mode0(True, make_face(0.62, 0.5), rest_face=rest)
    xa, xb = np.where(_red(a))[1].mean(), np.where(_red(b))[1].mean()
    assert abs((xb - xa) - 0.12 * W) < 10


def test_modus0_ohne_kopfverfolgung_augen_bleiben_auf_den_markern_und_aufrecht():
    rest = make_face(0.5, 0.4)
    assets = synth_assets()
    # erwartete Marker-Position aus der Ruhelage
    eyes = sorted([make_face(0.5, 0.4)[C.EYE_A].mean(0) * [W, H], make_face(0.5, 0.4)[C.EYE_B].mean(0) * [W, H]],
                  key=lambda e: e[0])
    d0 = float(np.hypot(*(eyes[1] - eyes[0])))
    mid0 = (eyes[0] + eyes[1]) / 2
    k = (d0 / (H * .16)) * (H * .6 / assets.head.h)
    a = assets.head_markers
    pv = ((a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2)
    for moved in (rest, make_face(0.62, 0.5, roll=0.3, scale=1.3)):
        out = _mode0(False, moved, rest_face=rest)
        for m in (0, 1):
            x = mid0[0] + (a[m][0] - pv[0]) * assets.head.w * k
            y = mid0[1] + (a[m][1] - pv[1]) * assets.head.h * k
            assert is_green(out[int(round(y)), int(round(x))]), f"Marker {m} bei {moved[0]}"


def test_modus0_ohne_kopfverfolgung_ausschnitt_groesse_bleibt_konstant():
    rest = make_face(0.5, 0.4)
    near = make_face(0.5, 0.4, scale=1.3)

    def green_area(o):
        return int(((o[..., 1] > 200) & (o[..., 0] < 60) & (o[..., 2] < 60)).sum())

    # feather=0: sonst verfaelscht die feste Kantenbreite (in Kamerapixeln) die Flaeche der winzigen Test-Augen
    a = green_area(_mode0(False, rest, feather=0))
    b = green_area(_mode0(False, near, rest_face=rest, feather=0))
    assert 0.9 < b / a < 1.1, f"Ausschnittsgroesse aendert sich mit dem Abstand: {a} -> {b}"
    # Gegenprobe: mit Kopfverfolgung waechst der Ausschnitt 1:1 mit (Bild skaliert mit)
    c = green_area(_mode0(True, near, rest_face=rest, feather=0))
    assert c / green_area(_mode0(True, rest, feather=0)) > 1.4


def test_modus0_ohne_kopfverfolgung_ruhelage_neu_setzen_verschiebt_das_png():
    s = Settings(mode=0, background="#000000", mirror=False, track_head=False)
    r = Rig()
    r.set_rest_pose()
    r.render(cam(), make_face(0.5, 0.4), s, synth_assets())
    a = r.render(cam(), make_face(0.7, 0.4), s, synth_assets())
    r.set_rest_pose()                                           # Knopf "Ruhelage setzen"
    b = r.render(cam(), make_face(0.7, 0.4), s, synth_assets())
    xa, xb = np.where(_red(a))[1].mean(), np.where(_red(b))[1].mean()
    assert abs((xb - xa) - 0.2 * W) < 10


def test_track_head_wird_in_modus_1_und_2_ignoriert():
    for mode in (1, 2):
        face = make_face(0.58, 0.45, roll=0.2)
        outs = []
        for track in (True, False):
            r = Rig()
            r.set_rest_pose()
            s = Settings(mode=mode, mirror=False, track_head=track, background="#000000")
            r.render(cam(), make_face(), s, synth_assets())
            outs.append(r.render(cam(), face, s, synth_assets()))
        assert np.array_equal(*outs)

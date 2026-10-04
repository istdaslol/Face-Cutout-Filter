"""Oberflaeche offscreen: Modi, Regler, Marker ziehen, Dateien, Profile, Kamera-Kette."""
import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

import fakes
from gesichtsfilter import config as C
from gesichtsfilter.core.demo import demo_assets
from gesichtsfilter.core.raster import Sprite
from gesichtsfilter.core.settings import RigAssets, Settings
from gesichtsfilter.engine import Engine
from gesichtsfilter.io import profile as P
from gesichtsfilter.io.camera import CameraInfo
from gesichtsfilter.sysutil import app_data_dir
from gesichtsfilter.ui import main_window as mw
from helpers import pump, wait_for


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    """Fenster mit Attrappen; Datenordner und Dialoge sind umgeleitet."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(mw, "list_cameras", lambda: [CameraInfo("Test-Kamera", 0, 0)])
    boxes = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: boxes.append(a)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: boxes.append(a)))
    fakes.FakeGrabber.fail = fakes.FakeVcam.fail = fakes.FakeTracker.explode = False
    made = []

    def make():
        s, a = Settings(), RigAssets()
        e = Engine(s, a, tracker_factory=fakes.FakeTracker, grabber_factory=fakes.FakeGrabber,
                   vcam_factory=fakes.FakeVcam)
        w = mw.MainWindow(e, s, a)
        w.show()
        pump(30)
        made.append(w)
        return w, e, boxes

    yield make
    for w in made:
        w.close()


def send_mouse(widget, typ, x, y):
    ev = QMouseEvent(typ, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def drag(editor, frm, to):
    w, h = editor.width(), editor.height()
    send_mouse(editor, QEvent.Type.MouseButtonPress, frm[0] * w, frm[1] * h)
    send_mouse(editor, QEvent.Type.MouseMove, to[0] * w, to[1] * h)
    send_mouse(editor, QEvent.Type.MouseButtonRelease, to[0] * w, to[1] * h)


def test_startzustand(env):
    w, e, _ = env()
    assert w.settings.mode == C.DEFAULT_MODE and w.assets.head is not None
    assert len(w._mk_buttons) == 5 and w.cmb_cam.currentText() == "Test-Kamera"
    assert not w.btn_up2.isVisibleTo(w) and not w.s_hr.isVisibleTo(w)
    assert w.btn_rest.isVisibleTo(w)


def test_modi_umschalten_sichtbarkeit_marker_und_demo(env):
    w, e, _ = env()
    w.cmb_mode.setCurrentIndex(0)
    assert not w.btn_rest.isVisibleTo(w) and not w.s_follow.isVisibleTo(w) and len(w._mk_buttons) == 3
    w.cmb_mode.setCurrentIndex(2)
    assert w.btn_up2.isVisibleTo(w) and w.s_hr.isVisibleTo(w) and w.chk_behind.isVisibleTo(w)
    assert w.assets.body is not None and w.btn_up.text() == "Eigenes Kopf-PNG"
    assert [b.text() for b in w._mk_buttons.values()] == ["Auge links", "Auge rechts", "Mund", "Hals-Pivot"]
    assert w.settings.image_scale == 0.5 and w.sliders["image_scale"].value() == 0.5   # Demo-Startwert
    w.set_view("body")
    assert [b.text() for b in w._mk_buttons.values()] == ["Hals-Anker"] and w.editor.current == 0
    w.cmb_mode.setCurrentIndex(1)
    assert w.view == "main" and w.settings.image_scale == 1.0 and len(w._mk_buttons) == 5
    assert not w.btn_up2.isVisibleTo(w)


def test_regler_schreiben_in_settings_und_augen_mund_ausschnitt_getrennt(env):
    w, e, _ = env()
    em0, mm0 = w.settings.eye_margin, w.settings.mouth_margin
    assert (em0, mm0) == (C.DEFAULT_EYE_MARGIN, C.DEFAULT_MOUTH_MARGIN)
    w.sliders["eye_margin"]._s.setValue(w.sliders["eye_margin"]._s.value() + 30)
    assert abs(w.settings.eye_margin - (em0 + .30)) < 1e-6 and w.settings.mouth_margin == mm0
    w.sliders["mouth_margin"]._s.setValue(0)
    assert w.settings.mouth_margin == C.RANGES["mouth_margin"][0]
    w.sliders["feather"]._s.setValue(5)
    assert w.settings.feather == 5 and isinstance(w.settings.feather, int)
    for chk, key in ((w.chk_brows, "brows"), (w.chk_mirror, "mirror")):
        chk.setChecked(False)
        assert getattr(w.settings, key) is False
    w.cmb_bg.setCurrentIndex(1)
    assert w.settings.background == "#00ff00"
    w.cmb_track.setCurrentIndex(1)
    assert w.settings.track_every == 2
    w.spin_fps.setValue(20)
    assert e.fps_limit == 20


def test_marker_ziehen_aendert_die_gemeinsamen_assets(env):
    w, e, _ = env()
    mund = w.assets.head_markers[2][:]
    drag(w.editor, mund, (0.3, 0.6))
    assert w.assets.head_markers[2] == pytest.approx([0.3, 0.6], abs=0.01)
    assert w.editor.current == 2 and w._mk_buttons[2].isChecked()
    # Klick ins Leere setzt den aktuellen Marker dorthin
    send_mouse(w.editor, QEvent.Type.MouseButtonPress, 3, 3)
    send_mouse(w.editor, QEvent.Type.MouseButtonRelease, 3, 3)
    assert w.assets.head_markers[2][0] < 0.1
    w.reset_markers()
    assert w.assets.head_markers == C.DEFAULT_MARKERS


def test_datei_laden_merkt_marker_per_sidecar(env, tmp_path):
    w, e, boxes = env()
    png = tmp_path / "mein kopf äöü.png"
    demo_assets().head.save_png(png)
    w.load_file(str(png))
    assert w.src["main"] == {"kind": "file", "path": str(png)} and w.assets.head.w == 600
    drag(w.editor, w.assets.head_markers[0][:], (0.2, 0.2))
    assert P.sidecar_path(png).exists()
    w2, _, _ = env()
    w2.load_file(str(png))
    assert w2.assets.head_markers[0] == pytest.approx([0.2, 0.2], abs=0.01)
    # kaputte Datei -> Meldung statt Absturz
    kaputt = tmp_path / "kaputt.png"
    kaputt.write_bytes(b"kein bild")
    w2.load_file(str(kaputt))
    assert boxes and w2.assets.head.w == 600


def test_zwischenablage_bild_wird_sprite():
    img = QImage(4, 2, QImage.Format.Format_ARGB32)
    img.fill(0)
    img.setPixelColor(1, 0, __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(255, 0, 0, 255))
    sp = mw.qimage_to_sprite(img)
    assert (sp.w, sp.h) == (4, 2)
    assert sp.pm[0, 1].tolist() == [0, 0, 255, 255]          # BGRA: rot, deckend
    assert sp.pm[1, 3, 3] == 0                                  # transparent


def test_profil_roundtrip_mit_ui_sync_und_zwischenablage_export(env, tmp_path):
    w, e, boxes = env()
    w.cmb_mode.setCurrentIndex(2)
    w.sliders["eye_margin"]._s.setValue(10)
    w.settings.mouth_margin = 0.9
    w.chk_mirror.setChecked(False)
    w.spin_fps.setValue(24)
    w.paste_clipboard_sprite = None
    w._set_layer("main", Sprite.from_straight_bgra(np.full((20, 10, 4), 255, np.uint8)),
                 [m[:] for m in C.DEFAULT_MARKERS], {"kind": "clipboard"})
    prof = tmp_path / "p" / "test.json"
    prof.parent.mkdir()
    w._write_profile(prof)
    assert (prof.parent / "test_kopf.png").exists()                        # Zwischenablage-Bild abgelegt
    assert w.src["main"]["kind"] == "file"
    # neues Fenster, anderer Zustand, Profil laden
    w2, _, _ = env()
    w2.apply_profile(P.load_profile(prof))
    assert w2.settings.mode == 2 and w2.cmb_mode.currentIndex() == 2
    assert w2.settings.mirror is False and not w2.chk_mirror.isChecked()
    assert w2.settings.mouth_margin == pytest.approx(0.9)
    assert w2.sliders["mouth_margin"].value() == pytest.approx(0.9)
    assert w2.spin_fps.value() == 24 and w2.engine.fps_limit == 24
    assert (w2.assets.head.w, w2.assets.head.h) == (10, 20) and w2.btn_up2.isVisibleTo(w2)


def test_profil_mit_fehlender_bilddatei_laedt_den_rest(env, tmp_path):
    w, e, boxes = env()
    prof = tmp_path / "p.json"
    P.save_profile(prof, Settings(mode=1, feather=3), {}, {"kind": "file", "path": str(tmp_path / "weg.png")},
                   [[.1, .1]] * 5, None, [[.5, .1]])
    w.apply_profile(P.load_profile(prof))
    assert w.settings.feather == 3 and w.sliders["feather"].value() == 3
    assert boxes and "weg.png" in boxes[-1][2] and w.assets.head is not None   # alte Demo bleibt


def test_alte_session_mit_margin_wird_gelesen(env, tmp_path):
    (app_data_dir() / "zuletzt.json").write_text(
        '{"kind": "gesichtsfilter-profil", "version": 1, "settings": {"margin": 1.5, "mode": 0}}',
        encoding="utf-8")
    w, e, _ = env()
    assert w.settings.mode == 0 and w.settings.eye_margin == pytest.approx(1.5)
    assert w.settings.mouth_margin == pytest.approx(1.6)


def test_sitzung_wird_beim_schliessen_gespeichert(env, tmp_path):
    w, e, _ = env()
    w.sliders["feather"]._s.setValue(11)
    w.close()
    assert (app_data_dir() / "zuletzt.json").exists()
    w2, _, _ = env()
    assert w2.settings.feather == 11 and w2.sliders["feather"].value() == 11


def test_kamera_und_virtuelle_kamera_bedienung(env):
    w, e, boxes = env()
    e.start()
    assert not w.btn_vcam.isEnabled()
    w.toggle_camera()
    assert wait_for(lambda: w._cam_running)
    assert w.btn_cam.text() == "Kamera stoppen" and w.btn_vcam.isEnabled()
    assert wait_for(lambda: w.preview._img is not None)                 # Vorschau kommt an
    assert wait_for(lambda: "fps" in w.lbl_stats.text())                # Statistik kommt an
    w.btn_vcam.click()
    assert wait_for(lambda: "<b>an</b>" in w.lbl_vcam.text())          # Antwort der Engine abwarten
    assert w.btn_vcam.isChecked() and w.btn_vcam.text() == "Virtuelle Kamera stoppen"
    assert "Fake Virtual Camera" in w.lbl_vcam.text()
    w.btn_rest.click()
    w.btn_vcam.click()
    assert wait_for(lambda: "<b>an</b>" not in w.lbl_vcam.text())
    assert not w.btn_vcam.isChecked() and w.btn_vcam.text() == "Virtuelle Kamera starten"
    w.toggle_camera()
    assert wait_for(lambda: not w._cam_running)
    assert w.btn_cam.text() == "Kamera starten" and not w.btn_vcam.isEnabled() and w.preview._img is None
    # Fehler beim Oeffnen: Meldung, Button wieder bedienbar
    fakes.FakeGrabber.fail = True
    w.toggle_camera()
    assert wait_for(lambda: boxes)
    assert w.btn_cam.isEnabled() and w.btn_cam.text() == "Kamera starten"


def test_vorschau_flag_folgt_checkbox(env):
    w, e, _ = env()
    w.chk_prev.setChecked(False)
    assert e.preview_enabled is False
    w.chk_prev.setChecked(True)
    assert e.preview_enabled is True


# ---------------------------------------------------------------- Foto
def test_foto_knoepfe_nur_mit_kamera_und_ohne_countdown_anzeige(env, tmp_path, monkeypatch):
    w, e, boxes = env()
    assert w.btn_photo_t.text() == "Foto in 3 s"              # Standard-Verzoegerung laut config
    monkeypatch.setattr(C, "PHOTO_DELAY_S", 0.5)             # danach: Test soll nicht 3 s warten
    e.start()
    w._set_photo_dir(tmp_path / "fotos")
    assert not w.btn_photo.isEnabled() and not w.btn_photo_t.isEnabled()
    w.toggle_camera()
    assert wait_for(lambda: w._cam_running)
    assert w.btn_photo.isEnabled() and w.btn_photo_t.isEnabled()
    # Sofort-Foto
    w.btn_photo.click()
    assert wait_for(lambda: "Foto gespeichert" in w.lbl_status.text())
    assert len(list((tmp_path / "fotos").glob("Foto_*.png"))) == 1
    # Foto mit Verzoegerung: keine Anzeige, bis es gespeichert ist
    vorher = w.lbl_status.text()
    w.btn_photo_t.click()
    pump(250)
    assert w.lbl_status.text() == vorher and len(list((tmp_path / "fotos").glob("*.png"))) == 1
    assert wait_for(lambda: len(list((tmp_path / "fotos").glob("*.png"))) == 2, 5000)
    # Kamera aus -> Knoepfe aus
    w.toggle_camera()
    assert wait_for(lambda: not w._cam_running)
    assert not w.btn_photo.isEnabled() and not w.btn_photo_t.isEnabled()
    assert not boxes


# ---------------------------------------------------------------- Kopfverfolgung
def test_kopfverfolgung_checkbox_nur_im_einfach_modus_und_ruhelage_knopf(env):
    w, e, _ = env()
    # Modus 1: keine Checkbox, Ruhelage sichtbar
    assert not w.chk_track.isVisibleTo(w) and w.btn_rest.isVisibleTo(w)
    w.cmb_mode.setCurrentIndex(0)
    assert w.chk_track.isVisibleTo(w) and w.chk_track.isChecked()
    assert not w.btn_rest.isVisibleTo(w) and not w.s_follow.isVisibleTo(w)     # folgt dem Kopf -> keine Ruhelage noetig
    w.chk_track.setChecked(False)
    assert w.settings.track_head is False
    assert w.btn_rest.isVisibleTo(w) and "bleibt dort stehen" in w.lbl_rest.text()
    assert not w.s_follow.isVisibleTo(w)
    w.cmb_mode.setCurrentIndex(2)
    assert not w.chk_track.isVisibleTo(w) and w.btn_rest.isVisibleTo(w)
    assert "bleibt dort stehen" not in w.lbl_rest.text()
    w.cmb_mode.setCurrentIndex(0)
    assert w.btn_rest.isVisibleTo(w)                                            # track_head ist weiter aus
    w.chk_track.setChecked(True)
    assert not w.btn_rest.isVisibleTo(w)


def test_kopfverfolgung_wird_im_profil_gespeichert_und_geladen(env, tmp_path):
    w, e, _ = env()
    w.cmb_mode.setCurrentIndex(0)
    w.chk_track.setChecked(False)
    prof = tmp_path / "t.json"
    w._write_profile(prof)
    w2, _, _ = env()
    w2.apply_profile(P.load_profile(prof))
    assert w2.settings.track_head is False and not w2.chk_track.isChecked()
    assert w2.btn_rest.isVisibleTo(w2) and w2.settings.mode == 0


# ---------------------------------------------------------------- Virtuelle Kamera: Backend
def test_backend_auswahl_geht_an_engine_und_ins_profil(env, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "backend_options",
                        lambda: [("obs", "OBS Virtual Camera"), ("unitycapture", "Unity Capture")])
    w, e, boxes = env()
    items = [(w.cmb_vbackend.itemText(i), w.cmb_vbackend.itemData(i)) for i in range(w.cmb_vbackend.count())]
    assert items == [("Automatisch (erstes verf\u00fcgbares)", None), ("OBS Virtual Camera", "obs"),
                     ("Unity Capture", "unitycapture")]
    assert e.vcam_backend is None and e.vcam_device is None
    w.cmb_vbackend.setCurrentIndex(2)
    w.edit_vdevice.setText("  Gesichtsfilter Kamera ")
    assert (e.vcam_backend, e.vcam_device) == ("unitycapture", "Gesichtsfilter Kamera")
    # Start mit Attrappe: Optionen kommen an, Auswahl ist waehrenddessen gesperrt
    e.start()
    w.toggle_camera()
    assert wait_for(lambda: w._cam_running)
    w.btn_vcam.click()
    assert wait_for(lambda: "<b>an</b>" in w.lbl_vcam.text())
    assert e.vcam.started_with == ("unitycapture", "Gesichtsfilter Kamera")
    assert not w.cmb_vbackend.isEnabled() and not w.edit_vdevice.isEnabled()
    w.btn_vcam.click()
    assert wait_for(lambda: "<b>an</b>" not in w.lbl_vcam.text())
    assert w.cmb_vbackend.isEnabled() and w.edit_vdevice.isEnabled()
    # Profil
    prof = tmp_path / "b.json"
    w._write_profile(prof)
    raw = P.load_profile(prof)["performance"]
    assert raw["vcam_backend"] == "unitycapture" and raw["vcam_device"].strip() == "Gesichtsfilter Kamera"
    w2, e2, _ = env()
    w2.apply_profile(P.load_profile(prof))
    assert w2.cmb_vbackend.currentData() == "unitycapture" and e2.vcam_backend == "unitycapture"
    assert e2.vcam_device == "Gesichtsfilter Kamera" and w2.edit_vdevice.text().strip() == "Gesichtsfilter Kamera"


def test_profil_mit_unbekanntem_backend_faellt_auf_automatisch(env, tmp_path):
    w, e, _ = env()                                   # (Linux-Test-System kennt "obs" nicht -> Fall ist real)
    prof = tmp_path / "x.json"
    P.save_profile(prof, Settings(), {"vcam_backend": "gibt_es_nicht", "vcam_device": 5}, {"kind": "demo"},
                   [[.4, .27], [.6, .27], [.5, .4], [.5, .475], [.5, .59]], None, [[.5, .1]])
    w.apply_profile(P.load_profile(prof))
    assert w.cmb_vbackend.currentData() is None and e.vcam_backend is None
    assert w.edit_vdevice.text() == ""                # kein str -> ignoriert


# ---------------------------------------------------------------- Dropdown lesbar
def test_dropdown_eintrag_unter_der_maus_ist_lesbar(qapp, env):
    """Rendert das Popup wirklich und prueft Farben: Hover = orange mit dunkler Schrift,
    sonst helle Schrift auf dunklem Grund. (Vorher: dunkle Schrift auf dunklem Grund.)"""
    from gesichtsfilter.app import apply_theme
    apply_theme(qapp)
    try:
        w, e, _ = env()
        c = w.cmb_bg
        c.showPopup()
        pump(150)
        v = c.view()
        r = v.visualRect(v.model().index(1, 0))
        pos = QPointF(r.center())
        QApplication.sendEvent(v.viewport(), QMouseEvent(
            QEvent.Type.MouseMove, pos, v.viewport().mapToGlobal(pos.toPoint()),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        pump(150)
        img = v.window().grab().toImage()
        off = v.viewport().mapTo(v.window(), v.viewport().rect().topLeft())

        def row_pixels(i):
            rr = v.visualRect(v.model().index(i, 0))
            return [img.pixelColor(off.x() + x, off.y() + y) for y in range(rr.top() + 2, rr.bottom() - 2)
                    for x in range(rr.left() + 4, rr.right() - 4)]

        def lum(col):
            return 0.299 * col.red() + 0.587 * col.green() + 0.114 * col.blue()

        hover, other = row_pixels(1), row_pixels(2)
        assert hover[0].name() == "#ffb347" and other[0].name() == "#2a2723"
        assert min(lum(p) for p in hover) < 80, "Schrift im Hover-Eintrag nicht dunkel"
        assert max(lum(p) for p in other) > 180, "Schrift in normalem Eintrag nicht hell"
        c.hidePopup()
    finally:
        qapp.setStyleSheet("")

"""io/vcam.py: Backend-Auswahl und Fehlertexte, ohne echte virtuelle Kamera (pyvirtualcam wird ersetzt)."""
import sys
import types

import numpy as np
import pytest

from gesichtsfilter.io import vcam


@pytest.fixture
def fake_pvc(monkeypatch):
    """Ersetzt das Modul pyvirtualcam durch eine Attrappe, die ihre Argumente mitschreibt."""
    mod = types.ModuleType("pyvirtualcam")
    mod.PixelFormat = types.SimpleNamespace(BGR="BGR")
    mod.calls, mod.sent = [], []
    mod.error = None

    class Camera:
        device = "Fake-Geraet"

        def __init__(self, **kw):
            mod.calls.append(kw)
            if mod.error:
                raise RuntimeError(mod.error)
            self.closed = False

        def send(self, frame):
            mod.sent.append(frame.shape)

        def close(self):
            self.closed = True

    mod.Camera = Camera
    monkeypatch.setitem(sys.modules, "pyvirtualcam", mod)
    return mod


def test_automatisch_gibt_weder_backend_noch_geraet_weiter(fake_pvc):
    v = vcam.VirtualCamera()
    v.start(640, 360, 30)
    assert fake_pvc.calls == [dict(width=640, height=360, fps=30, fmt="BGR")]
    assert v.active and v.device == "Fake-Geraet"


def test_backend_und_geraet_werden_durchgereicht_leere_und_leerzeichen_nicht(fake_pvc):
    v = vcam.VirtualCamera()
    v.start(640, 360, 30, "unitycapture", "  Gesichtsfilter Kamera ")
    assert fake_pvc.calls[-1]["backend"] == "unitycapture" and fake_pvc.calls[-1]["device"] == "Gesichtsfilter Kamera"
    v.start(640, 360, 30, "", "   ")                                   # leer = automatisch
    assert "backend" not in fake_pvc.calls[-1] and "device" not in fake_pvc.calls[-1]


def test_start_stoppt_vorherige_kamera_und_senden_skaliert(fake_pvc):
    v = vcam.VirtualCamera()
    v.start(640, 360, 30)
    first = v._cam
    v.start(320, 180, 15)
    assert first.closed and v.size == (320, 180)
    v.send(np.zeros((360, 640, 3), np.uint8))                           # falsche Groesse -> wird angepasst
    assert fake_pvc.sent == [(180, 320, 3)]
    v.stop()
    assert not v.active
    v.send(np.zeros((10, 10, 3), np.uint8))                             # nach stop(): kein Absturz, kein Senden
    assert len(fake_pvc.sent) == 1


def test_fehler_wird_zu_verstaendlicher_meldung_mit_technischer_zeile(fake_pvc):
    fake_pvc.error = "'obs' backend: nicht installiert\n'unitycapture' backend: nicht installiert"
    v = vcam.VirtualCamera()
    with pytest.raises(vcam.VirtualCamError) as e:
        v.start(640, 360, 30, "obs", None)
    msg = str(e.value)
    assert "konnte nicht gestartet werden" in msg and "OBS Virtual Camera" in msg
    assert "Technische Meldung" in msg and "unitycapture' backend" in msg
    assert not v.active


def test_fehlertext_nennt_den_geraetenamen_hinweis_nur_mit_geraet(monkeypatch):
    monkeypatch.setattr(vcam.sys, "platform", "win32")
    mit = vcam.VirtualCamera._friendly(RuntimeError("x"), "unitycapture", "Mein Name")
    ohne = vcam.VirtualCamera._friendly(RuntimeError("x"), "unitycapture", None)
    assert "Ger\u00e4tename stimmt" in mit and "Ger\u00e4tename stimmt" not in ohne
    assert vcam.UNITY_DEFAULT_NAME in mit and "Unity Capture" in mit


@pytest.mark.parametrize("plat,keys", [("win32", ["obs", "unitycapture"]), ("darwin", ["obs"]),
                                       ("linux", ["v4l2loopback"])])
def test_backend_liste_je_system(monkeypatch, plat, keys):
    monkeypatch.setattr(vcam.sys, "platform", plat)
    assert [k for k, _ in vcam.backend_options()] == keys


def test_erkennung_ausserhalb_von_windows_ist_unbekannt_statt_falsch(monkeypatch):
    monkeypatch.setattr(vcam.sys, "platform", "darwin")
    assert vcam.obs_virtualcam_installed() is None and vcam.unity_capture_installed() is None
    assert vcam.any_backend_installed() is None            # unbekannt -> kein falscher "fehlt"-Hinweis


def test_any_backend_installed_logik(monkeypatch):
    monkeypatch.setattr(vcam.sys, "platform", "win32")
    for obs, unity, expected in ((False, False, False), (True, False, True), (False, True, True),
                                 (None, False, None), (None, True, True)):
        monkeypatch.setattr(vcam, "obs_virtualcam_installed", lambda o=obs: o)
        monkeypatch.setattr(vcam, "unity_capture_installed", lambda u=unity: u)
        assert vcam.any_backend_installed() is expected, (obs, unity)


def test_clsids_und_hinweistexte(monkeypatch):
    # CLSIDs stammen aus den Quelltexten von OBS bzw. Unity Capture (UnityCaptureFilter.cpp, 64 Bit)
    assert vcam.UNITY_CAPTURE_CLSID == "{5C2CD55C-92AD-4999-8666-912BD3E70010}"
    assert vcam.OBS_VCAM_CLSID == "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
    for plat, must in (("win32", ("OBS", "Unity Capture")), ("darwin", ("OBS",)), ("linux", ("v4l2loopback", "install.sh"))):
        monkeypatch.setattr(vcam.sys, "platform", plat)
        text = vcam.missing_hint()
        assert all(m in text for m in must) and "Vorschau" in text


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="nur Linux")
def test_v4l2loopback_pruefung_liefert_bool_oder_none():
    assert vcam.v4l2loopback_loaded() in (True, False, None)

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
    mod.fail_if = None          # optional: Funktion kw -> bool, bei True scheitert dieser Versuch

    class Camera:
        device = "Fake-Geraet"

        def __init__(self, **kw):
            mod.calls.append(kw)
            if mod.error:
                raise RuntimeError(mod.error)
            if mod.fail_if and mod.fail_if(kw):
                raise RuntimeError(f"Versuch mit {kw.get('backend', 'Automatik')} fehlgeschlagen")
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


# ---------------------------------------------------------------- Name aus dem Windows-Installer
@pytest.fixture
def installed(monkeypatch, tmp_path):
    """Simuliert die installierte Windows-Version: gefrorene .exe mit unitycapture_name.txt daneben."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Gesichtsfilter.exe"))
    f = tmp_path / vcam.UNITY_NAME_FILE

    def write(text, encoding="utf-8"):
        f.write_bytes(text.encode(encoding) if isinstance(text, str) else text)
    return write


def test_installierter_name_wird_gelesen_auch_mit_bom_und_umlauten(installed):
    installed("Gesichtsfilter K\u00e4mera \n", "utf-8-sig")        # BOM + Zeilenende + Umlaut
    assert vcam.installed_unity_name() == "Gesichtsfilter K\u00e4mera"
    installed("Ohne BOM")
    assert vcam.installed_unity_name() == "Ohne BOM"


def test_installierter_name_fehlt_leer_oder_nicht_installiert(installed, monkeypatch, tmp_path):
    assert vcam.installed_unity_name() is None                       # Datei fehlt
    installed("   \n")
    assert vcam.installed_unity_name() is None                       # leer
    installed("Name")
    monkeypatch.delattr(sys, "frozen")                               # Entwicklungsmodus
    assert vcam.installed_unity_name() is None


def test_unitycapture_ohne_geraet_nimmt_den_installierten_namen(fake_pvc, installed):
    installed("Mein Stream")
    vcam.VirtualCamera().start(640, 360, 30, "unitycapture", None)
    assert fake_pvc.calls[-1]["device"] == "Mein Stream" and fake_pvc.calls[-1]["backend"] == "unitycapture"


def test_ausdrueckliches_geraet_gewinnt_gegen_installierten_namen(fake_pvc, installed):
    installed("Mein Stream")
    vcam.VirtualCamera().start(640, 360, 30, "unitycapture", "Anderes")
    assert fake_pvc.calls[-1]["device"] == "Anderes" and len(fake_pvc.calls) == 1


def test_automatik_zweiter_versuch_mit_installiertem_namen(fake_pvc, installed):
    """pyvirtualcam probiert intern OBS und Unity Capture mit dem Standardnamen; bei eigenem Namen scheitert das."""
    installed("Mein Stream")
    fake_pvc.fail_if = lambda kw: "device" not in kw                 # nur mit Geraetenamen klappt es
    v = vcam.VirtualCamera()
    v.start(640, 360, 30)
    assert len(fake_pvc.calls) == 2 and "backend" not in fake_pvc.calls[0]
    assert fake_pvc.calls[1]["backend"] == "unitycapture" and fake_pvc.calls[1]["device"] == "Mein Stream"
    assert v.active


def test_automatik_klappt_der_erste_versuch_gibt_es_keinen_zweiten(fake_pvc, installed):
    installed("Mein Stream")
    vcam.VirtualCamera().start(640, 360, 30)
    assert len(fake_pvc.calls) == 1


def test_automatik_ohne_installierten_namen_nur_ein_versuch(fake_pvc):
    fake_pvc.error = "nichts da"
    with pytest.raises(vcam.VirtualCamError):
        vcam.VirtualCamera().start(640, 360, 30)
    assert len(fake_pvc.calls) == 1


def test_beide_versuche_scheitern_meldung_enthaelt_beide_fehler(fake_pvc, installed):
    installed("Mein Stream")
    fake_pvc.error = "kaputt"
    with pytest.raises(vcam.VirtualCamError) as e:
        vcam.VirtualCamera().start(640, 360, 30)
    assert len(fake_pvc.calls) == 2 and str(e.value).count("kaputt") == 2


def test_standardname_stimmt_mit_installer_ueberein():
    """UI-Standardname und Installer-Standardname (#define DefaultCamName) muessen identisch sein."""
    import re
    from pathlib import Path
    iss = (Path(__file__).resolve().parent.parent / "packaging" / "installer.iss").read_text(encoding="utf-8")
    m = re.search(r'^#define DefaultCamName "([^"]+)"', iss, re.M)
    assert m and m.group(1) == vcam.UNITY_DEFAULT_NAME


def test_version_ist_0_3():
    import gesichtsfilter
    assert gesichtsfilter.__version__.startswith("0.3")

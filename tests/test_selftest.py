"""--selftest: Pruefung ohne Kamera (wird auch fuer den gebauten Windows-Build verwendet)."""
import pytest

pytest.importorskip("PySide6")
from gesichtsfilter import __version__
from gesichtsfilter.app import main, selftest
from gesichtsfilter.paths import MODEL_REL, resource

MODELL_DA = resource(MODEL_REL).exists()


def test_selftest_bericht_und_ergebnis(tmp_path, capsys):
    report = tmp_path / "bericht.txt"
    code = selftest(str(report))
    text = report.read_text(encoding="utf-8")
    assert text.startswith(f"Gesichtsfilter {__version__} - Selbsttest")
    for name in ("OpenCV / NumPy", "MediaPipe (Programmteile)", "Rendern aller Modi",
                 "Virtuelle Kamera (pyvirtualcam)", "Oberflaeche (Qt)"):
        assert f"OK      {name}" in text, text
    assert capsys.readouterr().out == text                  # gleicher Text auf der Konsole
    if MODELL_DA:
        assert code == 0 and text.rstrip().endswith("ERGEBNIS: OK"), text
        assert "OK      Tracking mit Modell" in text
    else:
        # Ohne Modell schlagen genau die beiden Modell-Pruefungen fehl, mit lesbarer Meldung
        assert code == 1
        assert "FEHLER  Gesichtsmodell vorhanden" in text and "FEHLER  Tracking mit Modell" in text
        assert "ERGEBNIS: FEHLER (2: Gesichtsmodell vorhanden, Tracking mit Modell)" in text


def test_selftest_ueber_main_mit_und_ohne_berichtsdatei(tmp_path, capsys):
    report = tmp_path / "r.txt"
    assert main(["--selftest", str(report)]) in (0, 1) and report.exists()
    capsys.readouterr()
    main(["--selftest"])                                    # ohne Datei: nur Konsole
    assert "Selbsttest" in capsys.readouterr().out


def test_selftest_ein_fehler_beendet_die_pruefung_nicht(monkeypatch, tmp_path):
    import gesichtsfilter.core.rig as rig
    monkeypatch.setattr(rig.Rig, "render", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kaputt")))
    report = tmp_path / "r.txt"
    assert selftest(str(report)) == 1
    t = report.read_text(encoding="utf-8")
    assert "FEHLER  Rendern aller Modi: RuntimeError: kaputt" in t and "OK      Oberflaeche (Qt)" in t

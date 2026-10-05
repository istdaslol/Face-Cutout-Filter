"""Statische Pruefung der Paketierung (PyInstaller-Befehl, Inno-Setup-Skript, Unity-Capture-Pinning).

Der Windows-Installer selbst laesst sich nur unter Windows mit Inno Setup bauen; diese Tests fangen
die typischen Fehler vorher ab (fehlende Dateien, kaputte Klammern, Rueckfall von Ausschluessen).
"""
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PK = ROOT / "packaging"
ISS = (PK / "installer.iss").read_text(encoding="utf-8")


def load(name):
    spec = importlib.util.spec_from_file_location(name, PK / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pyinstaller_befehl():
    b = load("build")
    cmd = b.build_command()
    assert "--onedir" in cmd and "--onefile" not in cmd and "--windowed" in cmd and "--noupx" in cmd
    assert cmd[cmd.index("--collect-all") + 1] == "mediapipe"
    data = cmd[cmd.index("--add-data") + 1]
    assert data.endswith("face_landmarker.task" + b.os.pathsep + "models") or data.endswith(b.os.pathsep + "models")
    assert "--windowed" not in b.build_command(windowed=False)
    ex = [cmd[i + 1] for i, c in enumerate(cmd) if c == "--exclude-module"]
    assert ex and len(set(ex)) == len(ex)
    # Regression: mediapipe 1.0.1 importiert matplotlib beim Start; der Selbsttest des Builds hat es gezeigt
    assert not {"matplotlib", "numpy", "cv2", "mediapipe", "PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtCore"} & set(ex)


def test_ausschluesse_blockieren_keine_importe_des_programms():
    """Kein ausgeschlossenes Modul wird vom eigenen Code importiert."""
    b = load("build")
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))
    for mod in b.EXCLUDES:
        top = mod.split(".")[0]
        assert not re.search(rf"^\s*(import|from)\s+{re.escape(mod)}\b", code, re.M), mod
        if "." not in mod:
            assert not re.search(rf"^\s*(import|from)\s+{re.escape(top)}\b", code, re.M), mod


def test_installer_verweist_nur_auf_vorhandene_dateien():
    assert (ROOT / "assets" / "app.ico").exists() and (PK / "UnityCapture-LICENSE.txt").exists()
    assert 'SetupIconFile=..\\assets\\app.ico' in ISS
    for m in re.finditer(r'Source: "([^"{]+)"', ISS):
        assert (PK / m.group(1)).exists(), m.group(1)
    for dll in ("UnityCaptureFilter32.dll", "UnityCaptureFilter64.dll"):
        assert dll in ISS


def test_installer_grundeinstellungen():
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in ISS and "PrivilegesRequired=admin" in ISS
    assert re.search(r"^AppId=\{\{[0-9A-F-]{36}\}$", ISS, re.M)
    assert 'Name: "unity"' in ISS and "Flags: unchecked" in ISS          # Desktop-Symbol aus
    assert not re.search(r'Name: "unity".*Types: [^;]*standard', ISS)    # Unity Capture nicht vorausgewaehlt
    assert "German.isl" in ISS and "Gesichtsfilter-Setup-{#MyAppVersion}" in ISS


def test_installer_befehle_entsprechen_den_skripten_des_projekts():
    # Original InstallCustomName.bat: regsvr32 "<dll>" "/i:UnityCaptureName=<Name>"; Uninstall: regsvr32 /u "<dll>"
    assert '"/i:UnityCaptureName=' in ISS and "/s /u" in ISS
    assert "{syswow64}" in ISS and "{sys}" in ISS                       # 32-Bit-DLL mit 32-Bit-regsvr32


def test_installer_pascal_code_klammern_und_kommentare():
    code = ISS[ISS.index("[Code]"):]
    code_nostr = re.sub(r"'(?:[^']|'')*'", "''", code)                    # Zeichenketten entfernen
    code_nocomm = re.sub(r"//.*", "", code_nostr)
    assert "{" not in code_nocomm and "}" not in code_nocomm, "geschweifte Klammer ausserhalb von Text/Kommentar"
    opens = len(re.findall(r"\b(begin|try)\b", code_nocomm, re.I))       # try ... finally ... end braucht kein begin
    assert opens == len(re.findall(r"\bend\b", code_nocomm, re.I))
    for proc in ("InitializeWizard", "ShouldSkipPage", "NextButtonClick", "CurStepChanged", "CurUninstallStepChanged"):
        assert re.search(rf"\b(procedure|function) {proc}\b", code), proc


def test_installer_namensdatei_stimmt_mit_dem_programm_ueberein():
    from gesichtsfilter.io import vcam
    assert f'#define NameFile       "{vcam.UNITY_NAME_FILE}"' in ISS
    assert "SaveStringsToUTF8File" in ISS and "TArrayOfString" in ISS     # Inno: Array, keine TStringList
    assert "TStringList" not in ISS


def test_unitycapture_pinning():
    f = load("fetch_unitycapture")
    assert re.fullmatch(r"[0-9a-f]{40}", f.COMMIT) and f.COMMIT in f.URL
    assert set(f.FILES) == {"UnityCaptureFilter32.dll", "UnityCaptureFilter64.dll"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in f.FILES.values())
    assert f.COMMIT in (PK / "UnityCapture-LICENSE.txt").read_text(encoding="utf-8")
    for name, digest in f.FILES.items():                                   # falls schon geladen: Pruefsumme muss passen
        p = f.DEST / name
        if p.exists():
            assert hashlib.sha256(p.read_bytes()).hexdigest() == digest


def test_fetch_lehnt_falsche_pruefsumme_ab_und_nutzt_cache(tmp_path, monkeypatch):
    f = load("fetch_unitycapture")
    data = b"dll-inhalt"
    good = hashlib.sha256(data).hexdigest()

    class R:
        def __init__(self, d): self.d = d
        def read(self): return self.d
        def __enter__(self): return self
        def __exit__(self, *a): return False

    calls = []
    monkeypatch.setattr(f.urllib.request, "urlopen", lambda url, timeout: calls.append(url) or R(data))
    monkeypatch.setattr(f.time, "sleep", lambda s: None)
    assert (f.fetch("x.dll", good, tmp_path)).read_bytes() == data and len(calls) == 1
    f.fetch("x.dll", good, tmp_path)
    assert len(calls) == 1                                                  # Cache
    (tmp_path / "x.dll").write_bytes(b"manipuliert")
    f.fetch("x.dll", good, tmp_path)
    assert (tmp_path / "x.dll").read_bytes() == data                        # neu geladen
    with pytest.raises(SystemExit):
        f.fetch("y.dll", "0" * 64, tmp_path, retries=2)                     # Download passt nicht zur Pruefsumme
    assert not (tmp_path / "y.dll").exists()


def test_icon_ist_gueltig():
    ico = (ROOT / "assets" / "app.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00" and int.from_bytes(ico[4:6], "little") >= 6

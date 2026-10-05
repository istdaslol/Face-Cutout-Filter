"""Baut Gesichtsfilter mit PyInstaller im --onedir-Modus (ein Ordner, KEINE einzelne .exe).

Aufruf (im aktivierten Entwicklungs-venv, Projektordner):
    python packaging/build.py                  Build nach dist/Gesichtsfilter/
    python packaging/build.py --selftest       danach "Gesichtsfilter --selftest" ausfuehren (empfohlen)
    python packaging/build.py --print          nur den PyInstaller-Befehl anzeigen
    python packaging/build.py --console        Variante MIT Konsolenfenster (zum Fehlersuchen)

Der Befehl, den dieses Skript zusammenbaut, steht mit --print vollstaendig auf dem Bildschirm; die
Einstellungen (Excludes, collect-all, Daten) stehen als Konstanten direkt hier oben.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "Gesichtsfilter"
ENTRY = ROOT / "run.py"
MODEL = ROOT / "models" / "face_landmarker.task"
ICON_ICO = ROOT / "assets" / "app.ico"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

# Pakete, deren Dateien (Programmteile, native Bibliotheken, Daten) komplett mitgenommen werden.
# mediapipe: noetig (native Bibliotheken und Modelldaten werden nicht automatisch gefunden).
# cv2: PyInstaller kennt OpenCV ueber einen eigenen Hook; nur eintragen, falls ein Build Dateien vermisst.
COLLECT_ALL: List[str] = ["mediapipe"]

# Module, die das Programm nicht braucht, die aber als Abhaengigkeit von mediapipe & Co. mitkommen wuerden.
# Jeder Eintrag ist mit dem Selbsttest des gebauten Programms geprueft (siehe --selftest).
EXCLUDES: List[str] = [
    "tkinter", "_tkinter",
    # matplotlib NICHT ausschliessen: mediapipe 1.0.1 importiert es beim Start (Selbsttest hat das gezeigt).
    "jax", "jaxlib", "ml_dtypes", "opt_einsum", "scipy",
    "IPython", "jupyter", "notebook", "pytest", "_pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtSql", "PySide6.QtPdf",
]


def build_command(dist: Path = DIST, build: Path = BUILD, windowed: bool = True) -> List[str]:
    """Der vollstaendige PyInstaller-Aufruf als Liste (rein berechnet, fuehrt nichts aus)."""
    cmd = [sys.executable, "-m", "PyInstaller", str(ENTRY),
           "--name", APP_NAME,
           "--onedir",                       # ein Ordner mit .exe + Bibliotheken, NICHT --onefile
           "--noconfirm", "--clean",
           "--noupx",                        # UPX bricht gern Qt-/mediapipe-DLLs und erhoeht Virenscanner-Treffer
           "--paths", str(ROOT / "src"),
           "--distpath", str(dist), "--workpath", str(build / "work"), "--specpath", str(build),
           # Gesichtsmodell: liegt danach unter <Programm>/_internal/models/ (siehe paths.resource)
           "--add-data", f"{MODEL}{os.pathsep}models",
           ]
    if windowed:
        cmd.append("--windowed")             # kein Konsolenfenster
    if sys.platform == "win32" and ICON_ICO.exists():
        cmd += ["--icon", str(ICON_ICO)]
    for pkg in COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    return cmd


def ensure_model() -> None:
    if MODEL.exists() and MODEL.stat().st_size > 1_000_000:
        return
    print("Gesichtsmodell fehlt - lade es (tools/fetch_model.py) ...")
    subprocess.run([sys.executable, str(ROOT / "tools" / "fetch_model.py")], check=True)


def exe_path(dist: Path = DIST) -> Path:
    return dist / APP_NAME / (APP_NAME + (".exe" if sys.platform == "win32" else ""))


def dir_size_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink()) / 1e6


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", action="store_true", help="nur den PyInstaller-Befehl anzeigen")
    ap.add_argument("--selftest", action="store_true", help="nach dem Build 'Gesichtsfilter --selftest' ausfuehren")
    ap.add_argument("--console", action="store_true", help="mit Konsolenfenster bauen (zum Fehlersuchen)")
    a = ap.parse_args(argv)

    cmd = build_command(windowed=not a.console)
    if a.print:
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        return 0
    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller fehlt:  pip install -r requirements-dev.txt", file=sys.stderr)
        return 2
    ensure_model()
    shutil.rmtree(DIST / APP_NAME, ignore_errors=True)
    print("Baue", APP_NAME, "...")
    subprocess.run(cmd, check=True, cwd=ROOT)

    exe = exe_path()
    internal = exe.parent / "_internal"
    model = internal / "models" / "face_landmarker.task"
    if not exe.exists():
        print(f"Fehler: {exe} wurde nicht erzeugt.", file=sys.stderr)
        return 1
    if not model.exists():
        print(f"Fehler: Gesichtsmodell nicht im Build gefunden: {model}", file=sys.stderr)
        return 1
    print(f"\nFertig: {exe.parent}  ({dir_size_mb(exe.parent):.0f} MB)")

    if a.selftest:
        report = BUILD / "selftest.txt"
        report.unlink(missing_ok=True)
        print("Selbsttest des gebauten Programms ...")
        # Das fensterlose Windows-Programm hat keine Konsole: Ergebnis steht in der Berichtsdatei.
        r = subprocess.run([str(exe), "--selftest", str(report)], timeout=300)
        print(report.read_text(encoding="utf-8") if report.exists() else "(kein Bericht geschrieben)")
        if r.returncode != 0:
            print("Selbsttest FEHLGESCHLAGEN.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

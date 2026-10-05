"""Baut die Setup.exe lokal (Windows): Modell + Unity-Capture holen, PyInstaller, Selbsttest, Inno Setup.

Aufruf (Projektordner, aktiviertes Entwicklungs-venv):
    python packaging/make_installer.py
    python packaging/make_installer.py --skip-build     nur Inno Setup (dist/ ist schon da)

Voraussetzung: Inno Setup 6 (iscc.exe). Wird im PATH und unter "C:\\Program Files (x86)\\Inno Setup 6" gesucht.
Ergebnis: installer_out/Gesichtsfilter-Setup-<Version>.exe
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))


def find_iscc() -> str:
    found = shutil.which("iscc")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            for sub in ("Inno Setup 6", r"Programs\Inno Setup 6"):
                p = Path(base) / sub / "ISCC.exe"
                if p.exists():
                    return str(p)
    raise SystemExit("Inno Setup 6 (iscc.exe) nicht gefunden. Installation: https://jrsoftware.org/isdl.php")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-build", action="store_true", help="PyInstaller-Schritt ueberspringen")
    a = ap.parse_args()
    from gesichtsfilter import __version__

    py = sys.executable
    subprocess.run([py, str(HERE / "fetch_unitycapture.py")], check=True)
    if not a.skip_build:
        subprocess.run([py, str(HERE / "build.py"), "--selftest"], check=True, cwd=ROOT)
    iscc = find_iscc()
    subprocess.run([iscc, f"/DMyAppVersion={__version__}", str(HERE / "installer.iss")], check=True, cwd=ROOT)
    out = ROOT / "installer_out" / f"Gesichtsfilter-Setup-{__version__}.exe"
    print(f"\nFertig: {out}  ({out.stat().st_size / 1e6:.0f} MB)" if out.exists() else "\nFehler: Setup.exe fehlt.")
    return 0 if out.exists() else 1


if __name__ == "__main__":
    sys.exit(main())

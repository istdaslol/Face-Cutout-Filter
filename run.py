"""Startskript (Entwicklung und PyInstaller-Einstiegspunkt)."""
import sys
from pathlib import Path

# Entwicklung: src/ in den Suchpfad (im PyInstaller-Paket nicht noetig, aber harmlos)
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from gesichtsfilter.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

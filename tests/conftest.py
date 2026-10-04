import os
import sys
from pathlib import Path

# Qt ohne Bildschirm testen (CI, Sandbox)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# src/ in den Suchpfad, damit "gesichtsfilter" ohne Installation importierbar ist
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

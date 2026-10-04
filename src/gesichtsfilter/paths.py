"""Pfad-Helfer. Funktioniert im Entwicklungsmodus und im PyInstaller-Paket."""
import sys
from pathlib import Path


def resource(rel_path: str) -> Path:
    """Liefert den absoluten Pfad einer mitgelieferten Datei.

    Im PyInstaller-Paket liegen Daten unter sys._MEIPASS, in der Entwicklung
    relativ zum Projektordner (zwei Ebenen ueber diesem Paket).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[2]
    return Path(base) / rel_path


MODEL_REL = "models/face_landmarker.task"

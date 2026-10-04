"""Laedt das MediaPipe-Gesichtsmodell EINMALIG fuer Entwicklung/Build herunter.

Die fertige Anwendung laedt zur Laufzeit NICHTS aus dem Internet. Das Modell
wird mit PyInstaller in den Installer gepackt (siehe packaging/).

Aufruf:  python tools/fetch_model.py
"""
import sys
import urllib.request
from pathlib import Path

# Dieselbe Modelldatei wie in der HTML-Version (float16, Version 1).
URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
       "face_landmarker/float16/1/face_landmarker.task")
ZIEL = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"
MIN_BYTES = 1_000_000  # Plausibilitaetscheck gegen Fehlerseiten


def main() -> int:
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    if ZIEL.exists() and ZIEL.stat().st_size > MIN_BYTES:
        print(f"Modell vorhanden: {ZIEL} ({ZIEL.stat().st_size} Bytes)")
        return 0
    print(f"Lade {URL} ...")
    urllib.request.urlretrieve(URL, ZIEL)
    groesse = ZIEL.stat().st_size
    if groesse < MIN_BYTES:
        ZIEL.unlink()
        print("Fehler: Datei zu klein, Download unvollstaendig.")
        return 1
    print(f"Fertig: {ZIEL} ({groesse} Bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Laedt die Unity-Capture-Filter fuer den Windows-Installer (optionale Komponente).

Gepinnt auf einen festen Commit und per SHA256 geprueft: Eine Aenderung im Repo des Autors oder eine
Manipulation unterwegs landet so nicht unbemerkt im Installer. Die DLLs werden NICHT eingecheckt,
sondern beim Bauen geholt (packaging/unitycapture/, steht in .gitignore).

Aufruf:  python packaging/fetch_unitycapture.py
Lizenz:  MIT (siehe packaging/UnityCapture-LICENSE.txt, wird mit installiert).
"""
import hashlib
import sys
import time
import urllib.request
from pathlib import Path

COMMIT = "3ed54c325e0ad71afcf4f246c07e5e17b3d7f2d2"
URL = f"https://raw.githubusercontent.com/schellingb/UnityCapture/{COMMIT}/Install/{{name}}"
# Dateiname -> SHA256 (am genannten Commit geprueft)
FILES = {
    "UnityCaptureFilter32.dll": "aa3ebdf03dea7f3aab3dd7b724751f49ed71672256b57c6a19aa6809cabf30ba",
    "UnityCaptureFilter64.dll": "72812f5363d8ecb45632253f8c8c888844b1b62e27616f3c8cc21064ccde25e5",
}
DEST = Path(__file__).resolve().parent / "unitycapture"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, expected: str, dest: Path = DEST, retries: int = 3) -> Path:
    target = dest / name
    if target.exists() and sha256(target) == expected:
        return target
    dest.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(URL.format(name=name), timeout=60) as r:
                data = r.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"SHA256 von {name} stimmt nicht (Download beschaedigt oder veraendert)")
            target.write_bytes(data)
            return target
        except Exception as e:      # Netzfehler und Pruefsumme gleich behandeln: erneut versuchen
            last = e
            time.sleep(2 * attempt)
    raise SystemExit(f"Fehler: {name} konnte nicht geladen werden: {last}")


def main() -> int:
    for name, digest in FILES.items():
        p = fetch(name, digest)
        print(f"OK {p.name}  {p.stat().st_size} Bytes  sha256 {digest[:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Speichern/Laden von Einstellungen und Markern als JSON.

Zwei Arten von Dateien:
  * Profil       (*.json): Einstellungen + beide Bilder (als Verweis) + alle Marker.
  * Marker-Speicher: die Marker je Bild, automatisch im Datenordner des Programms
    (%APPDATA%\\Gesichtsfilter\\marker\\<SHA256 der Bilddatei>.json). Zugeordnet wird ueber die
    Pruefsumme des Dateiinhalts: Umbenennen oder Verschieben des Bildes ist egal, ein veraendertes
    Bild bekommt neue Marker. Neben den Bildern wird nichts mehr abgelegt.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import List, Optional

from ..sysutil import app_data_dir

PROFILE_VERSION = 1
PROFILE_KIND = "gesichtsfilter-profil"


def _markers_ok(m, n_min: int, n_max: int) -> Optional[List[List[float]]]:
    """Prueft/saeubert eine Markerliste. None bei Unsinn."""
    try:
        out = [[min(1.0, max(0.0, float(p[0]))), min(1.0, max(0.0, float(p[1])))] for p in m]
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    return out if n_min <= len(out) <= n_max else None


# ---------------------------------------------------------------- Marker-Speicher
def image_hash(image_path) -> Optional[str]:
    """SHA256 des Dateiinhalts (None, wenn die Datei nicht lesbar ist)."""
    h = hashlib.sha256()
    try:
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def marker_store_dir() -> Path:
    return app_data_dir() / "marker"


def marker_file(image_path, store_dir=None) -> Optional[Path]:
    digest = image_hash(image_path)
    return None if digest is None else Path(store_dir or marker_store_dir()) / f"{digest}.json"


def _read_store(path: Path) -> dict:
    """{"5": [[x,y]...], "1": [[x,y]]}: Marker getrennt nach Anzahl (Kopf-Bild: 5, Koerper-Bild: 1),
    damit dasselbe Bild als Kopf und als Koerper verwendet werden kann."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        m = d["markers"]
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_markers(image_path, markers, store_dir=None) -> None:
    f = marker_file(image_path, store_dir)
    if f is None:
        return
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        store = _read_store(f)
        store[str(len(markers))] = markers
        f.write_text(json.dumps({"version": PROFILE_VERSION, "image": Path(image_path).name, "markers": store},
                                indent=1), encoding="utf-8")
    except OSError:
        pass  # Merkfunktion ist nur Komfort, nie ein Grund fuer einen Fehler


def _legacy_path(image_path) -> Path:
    p = Path(image_path)
    return p.with_name(p.name + ".marker.json")


def load_markers(image_path, n_min: int, n_max: int, store_dir=None) -> Optional[List[List[float]]]:
    """Gespeicherte Marker fuer dieses Bild (Anzahl zwischen n_min und n_max) oder None.

    Aeltere Versionen legten die Marker als <bild>.marker.json neben das Bild: Sie werden einmalig
    gelesen und in den Speicher uebernommen (die alte Datei bleibt unberuehrt liegen).
    """
    f = marker_file(image_path, store_dir)
    if f is None:
        return None
    store = _read_store(f)
    for n in range(n_min, n_max + 1):
        got = _markers_ok(store.get(str(n)), n_min, n_max)
        if got:
            return got
    try:
        legacy = _markers_ok(json.loads(_legacy_path(image_path).read_text(encoding="utf-8"))["markers"], n_min, n_max)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if legacy:
        save_markers(image_path, legacy, store_dir)
    return legacy


# ---------------------------------------------------------------- Profil
def _rel(path: str, base: Path) -> str:
    try:
        return os.path.relpath(path, base)
    except ValueError:  # anderes Laufwerk
        return path


def save_profile(path, settings, perf: dict, head_ref: dict, head_markers,
                 body_ref: Optional[dict], body_marker) -> None:
    """head_ref/body_ref: {"kind": "demo"|"peanut"|"file", "path": ...}."""
    path = Path(path)

    def conv(ref):
        if ref and ref.get("kind") == "file":
            return {"kind": "file", "path": _rel(ref["path"], path.parent)}
        return dict(ref) if ref else None

    data = {
        "kind": PROFILE_KIND,
        "version": PROFILE_VERSION,
        "settings": settings.to_dict(),
        "performance": perf,
        "head": conv(head_ref), "head_markers": head_markers,
        "body": conv(body_ref), "body_marker": body_marker,
    }
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def load_profile(path) -> dict:
    """Liest und prueft ein Profil. Wirft ValueError mit deutscher Meldung."""
    path = Path(path)
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"Profil nicht lesbar: {e}") from e
    if not isinstance(d, dict) or d.get("kind") != PROFILE_KIND:
        raise ValueError("Das ist keine Profildatei dieses Programms.")
    if int(d.get("version", 0)) > PROFILE_VERSION:
        raise ValueError("Das Profil stammt von einer neueren Programmversion.")

    def ref(r):
        if not isinstance(r, dict):
            return None
        if r.get("kind") == "file":
            p = Path(r.get("path", ""))
            return {"kind": "file", "path": str(p if p.is_absolute() else (path.parent / p).resolve())}
        if r.get("kind") in ("demo", "peanut"):
            return {"kind": r["kind"]}
        return None

    return {
        "settings": d.get("settings") if isinstance(d.get("settings"), dict) else {},
        "performance": d.get("performance") if isinstance(d.get("performance"), dict) else {},
        "head": ref(d.get("head")),
        "head_markers": _markers_ok(d.get("head_markers"), 5, 5),
        "body": ref(d.get("body")),
        "body_marker": _markers_ok(d.get("body_marker"), 1, 1),
    }

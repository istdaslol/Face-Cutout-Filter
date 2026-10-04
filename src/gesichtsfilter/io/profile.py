"""Speichern/Laden von Einstellungen und Markern als JSON.

Zwei Arten von Dateien:
  * Profil   (*.json): Einstellungen + beide Bilder (als Verweis) + alle Marker.
  * Sidecar  (<bild>.marker.json): nur die Marker EINES Bildes, wird automatisch
    neben dem Bild abgelegt und beim naechsten Laden desselben Bildes gelesen.
"""
import json
import os
from pathlib import Path
from typing import List, Optional

PROFILE_VERSION = 1
PROFILE_KIND = "gesichtsfilter-profil"


def _markers_ok(m, n_min: int, n_max: int) -> Optional[List[List[float]]]:
    """Prueft/saeubert eine Markerliste. None bei Unsinn."""
    try:
        out = [[min(1.0, max(0.0, float(p[0]))), min(1.0, max(0.0, float(p[1])))] for p in m]
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    return out if n_min <= len(out) <= n_max else None


# ---------------------------------------------------------------- Sidecar
def sidecar_path(image_path) -> Path:
    p = Path(image_path)
    return p.with_name(p.name + ".marker.json")


def save_sidecar(image_path, markers) -> None:
    try:
        sidecar_path(image_path).write_text(
            json.dumps({"version": PROFILE_VERSION, "markers": markers}, indent=1), encoding="utf-8")
    except OSError:
        pass  # z.B. schreibgeschuetzter Ordner: dann eben ohne Merkfunktion


def load_sidecar(image_path, n_min: int, n_max: int) -> Optional[List[List[float]]]:
    try:
        d = json.loads(sidecar_path(image_path).read_text(encoding="utf-8"))
        return _markers_ok(d["markers"], n_min, n_max)
    except (OSError, ValueError, KeyError, TypeError):
        return None


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

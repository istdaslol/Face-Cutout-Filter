"""Einstellungen und Bild-/Marker-Daten (ohne UI)."""
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from .. import config as C
from .raster import Sprite


@dataclass
class Settings:
    """Alle Regler/Optionen. Standardwerte stehen in config.py."""
    mode: int = C.DEFAULT_MODE              # 0 Einfach, 1 Ein PNG, 2 Zwei PNGs
    follow: float = C.DEFAULT_FOLLOW        # Kopf folgt (Staerke)
    image_scale: float = C.DEFAULT_IMAGE_SCALE
    head_ratio: float = C.DEFAULT_HEAD_RATIO
    eye_scale: float = C.DEFAULT_EYE_SCALE
    mouth_scale: float = C.DEFAULT_MOUTH_SCALE
    eye_margin: float = C.DEFAULT_EYE_MARGIN      # Augen-Ausschnitt (Rand)
    mouth_margin: float = C.DEFAULT_MOUTH_MARGIN  # Mund-Ausschnitt (Rand)
    feather: float = C.DEFAULT_FEATHER      # Weiche Kante
    brows: bool = C.DEFAULT_BROWS
    mirror: bool = C.DEFAULT_MIRROR
    behind: bool = C.DEFAULT_BEHIND         # Kopf hinter Koerper (nur Modus 2)
    background: str = C.DEFAULT_BACKGROUND  # "cam" oder "#rrggbb"
    track_every: int = C.DEFAULT_TRACK_EVERY

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        """Unbekannte Schluessel werden ignoriert (Vorwaertskompatibilitaet).

        Alte Profile kennen nur "margin" (Mund war immer +0.1): wird umgerechnet.
        """
        d = dict(d)
        if "margin" in d:
            old = d.pop("margin")
            try:
                d.setdefault("eye_margin", float(old))
                d.setdefault("mouth_margin", float(old) + C.LEGACY_MOUTH_EXTRA)
            except (TypeError, ValueError):
                pass
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class RigAssets:
    """Kopf-Bild (+ optional Koerper-Bild) samt Markern (relativ 0..1)."""
    head: Optional[Sprite] = None
    head_markers: List[List[float]] = field(
        default_factory=lambda: [m[:] for m in C.DEFAULT_MARKERS])
    body: Optional[Sprite] = None
    body_marker: List[List[float]] = field(
        default_factory=lambda: [m[:] for m in C.DEFAULT_BODY_MARKER])

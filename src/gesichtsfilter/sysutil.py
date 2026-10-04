"""Kleine Systemhelfer: Prozesspriorit\u00e4t und App-Datenordner."""
import os
import sys
from pathlib import Path

APP_NAME = "Gesichtsfilter"


def set_low_priority(enabled: bool) -> None:
    """Niedrigere Prozessprioritaet, damit ein nebenbei laufendes Spiel Vorrang hat."""
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL, NORMAL = 0x00004000, 0x00000020
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL if enabled else NORMAL)
        elif enabled:
            os.nice(5)
    except Exception:
        pass  # Prioritaet ist nur eine Optimierung, nie ein Grund abzustuerzen


def app_data_dir() -> Path:
    """%APPDATA%\\Gesichtsfilter (Windows) bzw. ~/.gesichtsfilter."""
    base = os.environ.get("APPDATA")
    p = Path(base) / APP_NAME if base else Path.home() / ".gesichtsfilter"
    p.mkdir(parents=True, exist_ok=True)
    return p

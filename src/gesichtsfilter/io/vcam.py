"""Virtuelle Kamera ueber pyvirtualcam (pyvirtualcam 0.14.0).

Unterstuetzte Backends (Namen wie in pyvirtualcam):
  * "obs"           Windows/macOS  OBS Virtual Camera (OBS Studio ab Version 26)
  * "unitycapture"  Windows        Unity Capture (DirectShow-Filter, auch mit eigenem Namen)
  * "v4l2loopback"  Linux          Kernelmodul v4l2loopback (/dev/videoN)
Ohne Angabe probiert pyvirtualcam alle verfuegbaren Backends der Reihe nach durch.
"""
import sys
from typing import List, Optional, Tuple

import cv2
import numpy as np

# CLSID des DirectShow-Filters "OBS Virtual Camera" (wird von OBS registriert)
OBS_VCAM_CLSID = "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
# CLSID des 64-Bit-Filters von Unity Capture (aus dem Quelltext: UnityCaptureFilter.cpp)
UNITY_CAPTURE_CLSID = "{5C2CD55C-92AD-4999-8666-912BD3E70010}"
UNITY_DEFAULT_NAME = "Unity Video Capture"

BACKEND_LABELS = {
    "obs": "OBS Virtual Camera",
    "unitycapture": "Unity Capture",
    "v4l2loopback": "v4l2loopback (Linux)",
}


class VirtualCamError(RuntimeError):
    """Virtuelle Kamera nicht startbar (Text ist fuer Anwender gedacht)."""


# ---------------------------------------------------------------- Erkennung
def backend_options() -> List[Tuple[str, str]]:
    """(Schluessel, Anzeigename) der Backends, die es auf diesem System gibt."""
    if sys.platform == "win32":
        keys = ["obs", "unitycapture"]
    elif sys.platform == "darwin":
        keys = ["obs"]
    else:
        keys = ["v4l2loopback"]
    return [(k, BACKEND_LABELS[k]) for k in keys]


def _clsid_registered(clsid: str) -> Optional[bool]:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}", 0, winreg.KEY_READ | view):
                return True
        except OSError:
            continue
    return False


def obs_virtualcam_installed() -> Optional[bool]:
    return _clsid_registered(OBS_VCAM_CLSID)


def unity_capture_installed() -> Optional[bool]:
    return _clsid_registered(UNITY_CAPTURE_CLSID)


def v4l2loopback_loaded() -> Optional[bool]:
    """Linux: ist das Kernelmodul geladen? (/proc/modules)"""
    if not sys.platform.startswith("linux"):
        return None
    try:
        with open("/proc/modules", encoding="ascii", errors="ignore") as f:
            return any(line.split(" ", 1)[0] == "v4l2loopback" for line in f)
    except OSError:
        return None


def backend_installed(key: str) -> Optional[bool]:
    """True/False, falls pruefbar, sonst None. Heuristik: das Starten entscheidet am Ende."""
    return {"obs": obs_virtualcam_installed, "unitycapture": unity_capture_installed,
            "v4l2loopback": v4l2loopback_loaded}.get(key, lambda: None)()


def any_backend_installed() -> Optional[bool]:
    """True, wenn mindestens ein Backend da ist; False, wenn alle pruefbaren fehlen; sonst None."""
    states = [backend_installed(k) for k, _ in backend_options()]
    if any(s is True for s in states):
        return True
    if states and all(s is False for s in states):
        return False
    return None


def missing_hint() -> str:
    """Hinweistext, wenn keine virtuelle Kamera gefunden wurde."""
    if sys.platform == "win32":
        return (
            "Es wurde keine virtuelle Kamera gefunden.\n\n"
            "Zum Senden an Zoom, Discord, Teams usw. wird eine davon ben\u00f6tigt:\n"
            "\u2022 OBS Studio (ab Version 26). Nach der Installation kann OBS geschlossen bleiben.\n"
            "\u2022 Unity Capture (kann mit dem Installer dieses Programms mitinstalliert werden).\n\n"
            "Die Vorschau funktioniert auch ohne.")
    if sys.platform == "darwin":
        return ("Es wurde keine virtuelle Kamera gefunden. Installiere OBS Studio (ab Version 26).\n\n"
                "Die Vorschau funktioniert auch ohne.")
    return (
        "Das Kernelmodul v4l2loopback ist nicht geladen, deshalb gibt es keine virtuelle Kamera.\n\n"
        "Einrichten mit dem mitgelieferten install.sh, oder von Hand:\n"
        "  sudo apt install v4l2loopback-dkms\n"
        "  sudo modprobe v4l2loopback devices=1 video_nr=10 card_label=\"Gesichtsfilter\" exclusive_caps=1\n\n"
        "Die Vorschau funktioniert auch ohne.")


# ---------------------------------------------------------------- Kamera
class VirtualCamera:
    """Schmale Huelle um pyvirtualcam.Camera mit verstaendlichen Fehlern."""

    def __init__(self):
        self._cam = None
        self.size = (0, 0)

    @property
    def active(self) -> bool:
        return self._cam is not None

    @property
    def device(self) -> str:
        return getattr(self._cam, "device", "") if self._cam else ""

    @property
    def backend(self) -> str:
        return getattr(self._cam, "backend", "") if self._cam else ""

    def start(self, width: int, height: int, fps: int,
              backend: Optional[str] = None, device: Optional[str] = None) -> None:
        """backend=None: automatisch. device: z.B. Unity-Capture-Name oder /dev/video10."""
        if self._cam is not None:
            self.stop()
        backend = backend or None
        device = (device or "").strip() or None
        try:
            import pyvirtualcam
        except Exception as e:  # pragma: no cover
            raise VirtualCamError(f"pyvirtualcam konnte nicht geladen werden: {e}") from e
        kwargs = dict(width=width, height=height, fps=int(fps), fmt=pyvirtualcam.PixelFormat.BGR)
        if backend:
            kwargs["backend"] = backend
        if device:
            kwargs["device"] = device
        try:
            self._cam = pyvirtualcam.Camera(**kwargs)
        except Exception as e:
            self._cam = None
            raise VirtualCamError(self._friendly(e, backend, device)) from e
        self.size = (width, height)

    @staticmethod
    def _friendly(err: Exception, backend: Optional[str], device: Optional[str]) -> str:
        what = BACKEND_LABELS.get(backend or "", "keines der Backends")
        head = f"Die virtuelle Kamera konnte nicht gestartet werden ({what}).\n\n"
        if sys.platform == "win32":
            tips = ("Pr\u00fcfe bitte:\n"
                    "\u2022 OBS Studio (ab 26) oder Unity Capture ist installiert.\n"
                    "\u2022 In OBS ist die \u201eVirtuelle Kamera\u201c nicht gleichzeitig gestartet.\n"
                    "\u2022 Kein anderes Programm belegt sie.\n"
                    + ("\u2022 Der Ger\u00e4tename stimmt exakt (bei Unity Capture: der bei der Installation "
                       f"vergebene Name, Standard \u201e{UNITY_DEFAULT_NAME}\u201c).\n" if device else ""))
        elif sys.platform == "darwin":
            tips = "Pr\u00fcfe bitte, dass OBS Studio installiert und die virtuelle Kamera aktiviert ist.\n"
        else:
            tips = ("Pr\u00fcfe bitte:\n"
                    "\u2022 Das Modul v4l2loopback ist geladen (install.sh richtet das ein).\n"
                    "\u2022 Du bist in der Gruppe \u201evideo\u201c (danach neu anmelden).\n"
                    "\u2022 Kein anderes Programm belegt das Ger\u00e4t.\n"
                    + ("\u2022 Der Pfad stimmt, z. B. /dev/video10.\n" if device else ""))
        return f"{head}{tips}\nTechnische Meldung:\n{err}"

    def send(self, frame_bgr: np.ndarray) -> None:
        if self._cam is None:
            return
        w, h = self.size
        if frame_bgr.shape[1] != w or frame_bgr.shape[0] != h:
            frame_bgr = cv2.resize(frame_bgr, (w, h))
        self._cam.send(np.ascontiguousarray(frame_bgr))

    def stop(self) -> None:
        if self._cam is not None:
            try:
                self._cam.close()
            finally:
                self._cam = None

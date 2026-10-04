"""Virtuelle Kamera (OBS Virtual Camera) ueber pyvirtualcam."""
import sys
from typing import Optional

import cv2
import numpy as np

# CLSID des DirectShow-Filters "OBS Virtual Camera" (wird von OBS registriert)
OBS_VCAM_CLSID = "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"

OBS_HINWEIS = (
    "Die OBS Virtual Camera wurde nicht gefunden.\n\n"
    "Zum Senden an Zoom, Discord, Teams usw. wird OBS Studio (ab Version 26) "
    "ben\u00f6tigt, weil es die virtuelle Kamera installiert. Du kannst OBS nach "
    "der Installation geschlossen lassen.\n\n"
    "Die Vorschau funktioniert auch ohne OBS.")


class VirtualCamError(RuntimeError):
    """Virtuelle Kamera nicht startbar (Text ist fuer Anwender gedacht)."""


def obs_virtualcam_installed() -> Optional[bool]:
    """True/False unter Windows; None, wenn nicht pruefbar (andere Systeme).

    Prueft nur die Registrierung des OBS-Filters. Ob das Starten klappt,
    zeigt letztlich erst VirtualCamera.start().
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{OBS_VCAM_CLSID}", 0,
                                winreg.KEY_READ | view):
                return True
        except OSError:
            continue
    return False


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

    def start(self, width: int, height: int, fps: int) -> None:
        if self._cam is not None:
            self.stop()
        try:
            import pyvirtualcam
        except Exception as e:  # pragma: no cover
            raise VirtualCamError(f"pyvirtualcam konnte nicht geladen werden: {e}") from e
        kwargs = dict(width=width, height=height, fps=int(fps), fmt=pyvirtualcam.PixelFormat.BGR)
        if sys.platform == "win32":
            kwargs["backend"] = "obs"
        try:
            self._cam = pyvirtualcam.Camera(**kwargs)
        except Exception as e:
            self._cam = None
            raise VirtualCamError(
                "Die virtuelle Kamera konnte nicht gestartet werden.\n\n"
                "Pr\u00fcfe bitte: \u2022 OBS Studio (ab 26) ist installiert. "
                "\u2022 In OBS ist die \u201eVirtuelle Kamera\u201c nicht gleichzeitig gestartet. "
                "\u2022 Kein anderes Programm belegt sie.\n\n"
                f"Technische Meldung: {e}") from e
        self.size = (width, height)

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

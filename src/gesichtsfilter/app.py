"""Programmstart: Logging, Design, Pruefungen, Hauptfenster."""
import logging
import logging.handlers
import os
import sys
import threading
from typing import List, Optional

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from . import __version__
from .core.settings import RigAssets, Settings
from .engine import Engine
from .io.vcam import any_backend_installed, missing_hint
from .sysutil import APP_NAME, app_data_dir, set_low_priority
from .ui.main_window import MainWindow

STYLE = """
QPushButton { padding: 6px 10px; border: 1px solid #4a453f; border-radius: 6px; background: #3a3631; }
QPushButton:hover { border-color: #ffb347; }
QPushButton:checked { background: #5a4a2a; border-color: #ffb347; }
QPushButton:disabled { color: #7d766b; background: #2f2c28; }
QPushButton#primary { background: #ffb347; color: #1a1a1a; font-weight: bold; border: none; }
QPushButton#primary:disabled { background: #6b5a3a; color: #2a2a2a; }
QComboBox, QSpinBox { padding: 5px; border: 1px solid #4a453f; border-radius: 6px; background: #2a2723; }
QComboBox QAbstractItemView { background: #2a2723; color: #f4efe6; border: 1px solid #4a453f; outline: 0;
    selection-background-color: #ffb347; selection-color: #1a1a1a; }
QComboBox QAbstractItemView::item { padding: 5px 8px; min-height: 22px; color: #f4efe6; background: #2a2723; }
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {
    background: #ffb347; color: #1a1a1a; }
QLineEdit { padding: 5px; border: 1px solid #4a453f; border-radius: 6px; background: #2a2723; }
QLineEdit:disabled { color: #7d766b; background: #2f2c28; }
QSlider::groove:horizontal { height: 4px; background: #4a453f; border-radius: 2px; }
QSlider::handle:horizontal { background: #ffb347; width: 14px; margin: -6px 0; border-radius: 7px; }
QToolTip { color: #f4efe6; background: #2a2723; border: 1px solid #4a453f; }
"""


def setup_logging():
    """Logdatei im Datenordner (hilfreich bei Fehlermeldungen von Anwendern)."""
    path = app_data_dir() / "log.txt"
    h = logging.handlers.RotatingFileHandler(path, maxBytes=500_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)
    return path


def apply_theme(app: QApplication):
    app.setStyle("Fusion")
    p = QPalette()
    for role, col in ((QPalette.ColorRole.Window, "#1f1d1a"), (QPalette.ColorRole.Base, "#2a2723"),
                      (QPalette.ColorRole.AlternateBase, "#2f2c28"), (QPalette.ColorRole.Button, "#3a3631"),
                      (QPalette.ColorRole.WindowText, "#f4efe6"), (QPalette.ColorRole.Text, "#f4efe6"),
                      (QPalette.ColorRole.ButtonText, "#f4efe6"), (QPalette.ColorRole.ToolTipBase, "#2a2723"),
                      (QPalette.ColorRole.ToolTipText, "#f4efe6"), (QPalette.ColorRole.Highlight, "#ffb347"),
                      (QPalette.ColorRole.HighlightedText, "#1a1a1a")):
        p.setColor(role, QColor(col))
    app.setPalette(p)
    app.setStyleSheet(STYLE)


def install_excepthooks(log_path):
    """Unerwartete Fehler anzeigen und protokollieren statt still abzustuerzen."""
    def show(exc_type, exc, tb):
        logging.getLogger("crash").error("Unbehandelter Fehler", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None and threading.current_thread() is threading.main_thread():
            QMessageBox.critical(None, "Unerwarteter Fehler",
                                 f"{exc_type.__name__}: {exc}\n\nDetails stehen in:\n{log_path}")

    sys.excepthook = show
    threading.excepthook = lambda a: show(a.exc_type, a.exc_value, a.exc_traceback)


def _check_vcam(parent):
    """Einmaliger Hinweis, wenn keine virtuelle Kamera gefunden wird (Vorschau geht trotzdem)."""
    if any_backend_installed() is not False:
        return
    cfg = QSettings(APP_NAME, APP_NAME)
    if cfg.value("vcam_hinweis_aus", False, type=bool):
        return
    box = QMessageBox(QMessageBox.Icon.Information, "Keine virtuelle Kamera gefunden", missing_hint(),
                      QMessageBox.StandardButton.Ok, parent)
    chk = QCheckBox("Diesen Hinweis nicht mehr anzeigen")
    box.setCheckBox(chk)
    box.exec()
    if chk.isChecked():
        cfg.setValue("vcam_hinweis_aus", True)


def selftest(report_path: Optional[str] = None) -> int:
    """Pruefung ohne Kamera: Ist dieses Programm (z.B. ein PyInstaller-Build) vollstaendig?

    Aufruf:  Gesichtsfilter.exe --selftest [bericht.txt]      (Rueckgabewert 0 = alles in Ordnung)
    Prueft Importe, OpenCV, das Gesichtsmodell samt MediaPipe, das Rendern aller Modi und Qt.
    Die Windows-Version hat kein Konsolenfenster, deshalb wird der Bericht auch in eine Datei geschrieben.
    """
    import numpy as np
    lines: List[str] = [f"Gesichtsfilter {__version__} - Selbsttest",
                        f"Python {sys.version.split()[0]}, gepackt: {bool(getattr(sys, 'frozen', False))}"]
    failed: List[str] = []

    def check(name, fn):
        try:
            detail = fn()
        except Exception as e:  # jede Art von Fehler soll im Bericht stehen, nicht das Programm beenden
            failed.append(name)
            lines.append(f"FEHLER  {name}: {type(e).__name__}: {e}")
        else:
            lines.append(f"OK      {name}" + (f": {detail}" if detail else ""))

    def c_opencv():
        import cv2
        a = np.zeros((40, 40, 3), np.uint8)
        cv2.fillPoly(a, [np.array([[5, 5], [30, 8], [20, 30]], np.int32)], (255, 255, 255), lineType=cv2.LINE_AA)
        cv2.GaussianBlur(a, (0, 0), 3)
        cv2.warpAffine(a, np.float64([[1, 0, 2], [0, 1, 2]]), (40, 40))
        return f"OpenCV {cv2.__version__}, NumPy {np.__version__}"

    def c_mediapipe():
        import mediapipe
        from mediapipe.tasks.python import BaseOptions, vision
        assert vision.FaceLandmarker and BaseOptions
        return f"mediapipe {mediapipe.__version__}"

    def c_model():
        from .paths import MODEL_REL, resource
        p = resource(MODEL_REL)
        if not p.exists():
            raise FileNotFoundError(f"fehlt: {p}")
        if p.stat().st_size < 1_000_000:
            raise ValueError(f"zu klein ({p.stat().st_size} Bytes): {p}")
        return f"{p.stat().st_size // 1024} KB"

    def c_tracker():
        from .core.tracker import FaceTracker
        t = FaceTracker()
        try:
            if t.detect(np.zeros((360, 640, 3), np.uint8)) is not None:
                raise AssertionError("Gesicht in leerem Bild erkannt")
        finally:
            t.close()
        return f"Modell geladen ({t.delegate_used})"

    def c_render():
        from .core.demo import demo_assets, peanut_assets
        from .core.rig import Rig
        from .core.synthetic import make_face
        cam = np.full((360, 640, 3), (90, 110, 70), np.uint8)
        face = make_face(0.5, 0.4, aspect=640 / 360)
        for mode, assets in ((0, demo_assets()), (1, peanut_assets()), (2, demo_assets(True))):
            r = Rig()
            r.set_rest_pose()
            out = r.render(cam, face, Settings(mode=mode, mirror=False, image_scale=0.5 if mode == 2 else 1.0),
                           assets)
            if out.shape != cam.shape or np.array_equal(out, cam):
                raise AssertionError(f"Modus {mode}: nichts eingeblendet")
        return "Modi 0, 1 und 2"

    def c_vcam():
        import pyvirtualcam
        from .io.vcam import backend_options
        return f"pyvirtualcam {pyvirtualcam.__version__}, Backends: " + ", ".join(k for k, _ in backend_options())

    def c_cameras():
        from .io.camera import list_cameras
        return f"{len(list_cameras())} Kamera(s) gefunden"

    def c_qt():
        import PySide6
        from PySide6.QtWidgets import QApplication
        from .core.demo import demo_assets
        from .ui.widgets import MarkerEditor, StyledCombo
        app = QApplication.instance() or QApplication([])
        a = demo_assets()
        ed = MarkerEditor()
        ed.resize(200, 200)
        ed.set_content(a.head, a.head_markers, [0, 1, 2], {i: ("x", "#fff", "L") for i in range(5)})
        box = StyledCombo()
        box.addItems(["a", "b"])
        if ed.grab().isNull() or box.grab().isNull():
            raise AssertionError("Widgets lassen sich nicht zeichnen")
        return f"PySide6 {PySide6.__version__}, Plattform: {app.platformName()}"

    check("OpenCV / NumPy", c_opencv)
    check("MediaPipe (Programmteile)", c_mediapipe)
    check("Gesichtsmodell vorhanden", c_model)
    check("Tracking mit Modell", c_tracker)
    check("Rendern aller Modi", c_render)
    check("Virtuelle Kamera (pyvirtualcam)", c_vcam)
    check("Kameras suchen", c_cameras)
    check("Oberflaeche (Qt)", c_qt)
    lines.append("ERGEBNIS: OK" if not failed else f"ERGEBNIS: FEHLER ({len(failed)}: {', '.join(failed)})")

    text = "\n".join(lines) + "\n"
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(text)
    if sys.stdout is not None:      # None in der Windows-Version ohne Konsole
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Windows-Version ohne Konsole (PyInstaller --windowed): stdout/stderr sind None. Bibliotheken, die dorthin
    # schreiben (absl, mediapipe), duerfen daran nicht scheitern.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    if "--selftest" in argv:
        i = argv.index("--selftest")
        path = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        return selftest(path)
    log_path = setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    install_excepthooks(log_path)
    apply_theme(app)

    settings, assets = Settings(), RigAssets()
    engine = Engine(settings, assets)
    win = MainWindow(engine, settings, assets)
    set_low_priority(win.chk_prio.isChecked())
    engine.start()
    win.show()
    QTimer.singleShot(400, lambda: _check_vcam(win))
    code = app.exec()
    engine.shutdown()
    return code

"""Programmstart: Logging, Design, Pruefungen, Hauptfenster."""
import logging
import logging.handlers
import sys
import threading

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from .core.settings import RigAssets, Settings
from .engine import Engine
from .io.vcam import OBS_HINWEIS, obs_virtualcam_installed
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


def _check_obs(parent):
    """Einmaliger Hinweis, wenn die OBS Virtual Camera fehlt (Vorschau geht trotzdem)."""
    if obs_virtualcam_installed() is not False:
        return
    cfg = QSettings(APP_NAME, APP_NAME)
    if cfg.value("obs_hinweis_aus", False, type=bool):
        return
    box = QMessageBox(QMessageBox.Icon.Information, "OBS Virtual Camera fehlt", OBS_HINWEIS,
                      QMessageBox.StandardButton.Ok, parent)
    chk = QCheckBox("Diesen Hinweis nicht mehr anzeigen")
    box.setCheckBox(chk)
    box.exec()
    if chk.isChecked():
        cfg.setValue("obs_hinweis_aus", True)


def main() -> int:
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
    QTimer.singleShot(400, lambda: _check_obs(win))
    code = app.exec()
    engine.shutdown()
    return code

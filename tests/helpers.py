"""Warte-Helfer fuer Qt-Tests.

WICHTIG: NICHT QTest.qWait() verwenden. Unter PySide6 haelt qWait die Python-GIL
fest, solange es wartet. Hintergrund-Threads (unsere Engine) kommen dann kaum noch
dran: ein Render-Aufruf dauerte in Tests bis zu 4 Sekunden statt 10 Millisekunden.
Die echte Anwendung ist nicht betroffen (app.exec() gibt die GIL frei).
"""
import time

from PySide6.QtWidgets import QApplication


def pump(ms: float) -> None:
    """Verarbeitet Qt-Ereignisse und wartet ms Millisekunden, ohne die GIL zu blockieren."""
    end = time.monotonic() + ms / 1000
    app = QApplication.instance()
    while True:
        app.processEvents()
        if time.monotonic() >= end:
            return
        time.sleep(0.005)


def wait_for(cond, ms=15000):
    """Wartet, bis cond() wahr ist. Bei Zeitueberschreitung gibt es eine Diagnose.

    wait_for.diag kann auf eine Funktion gesetzt werden, die den Zustand beschreibt.
    """
    import inspect
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        pump(10)
    if cond():
        return True
    try:
        what = inspect.getsource(cond).strip()
    except (OSError, TypeError):
        what = repr(cond)
    diag = wait_for.diag() if wait_for.diag else "(keine Diagnose)"
    raise AssertionError(f"Zeitueberschreitung nach {ms} ms bei: {what}\n{diag}")


wait_for.diag = None

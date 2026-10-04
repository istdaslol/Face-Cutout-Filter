"""Engine (Thread) mit Attrappen: Start/Stop, virtuelle Kamera, fps-Limit, Fehlerpfade."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

import fakes
from helpers import pump, wait_for
from gesichtsfilter.core.demo import demo_assets
from gesichtsfilter.core.settings import Settings
from gesichtsfilter.engine import Engine
from gesichtsfilter.io.camera import CameraInfo


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Collector(QObject):
    """Sammelt Signale in einem QObject, damit sie im Test-(UI-)Thread ankommen."""
    def __init__(self):
        super().__init__()
        self.previews, self.errors, self.started, self.stopped = [], [], [], 0
        self.vcam, self.stats, self.status = [], [], []

    @Slot(QImage)
    def on_preview(self, i): self.previews.append(i)
    @Slot(str, str)
    def on_error(self, t, x): self.errors.append((t, x))
    @Slot(int, int)
    def on_started(self, w, h): self.started.append((w, h))
    @Slot()
    def on_stopped(self): self.stopped += 1
    @Slot(bool, str)
    def on_vcam(self, a, d): self.vcam.append((a, d))
    @Slot(float, float, float)
    def on_stats(self, f, t, r): self.stats.append((f, t, r))
    @Slot(str)
    def on_status(self, s): self.status.append(s)


@pytest.fixture
def eng(qapp):
    fakes.FakeGrabber.fail = fakes.FakeVcam.fail = fakes.FakeTracker.explode = False
    s, a = Settings(mirror=False), demo_assets()
    e = Engine(s, a, tracker_factory=fakes.FakeTracker, grabber_factory=fakes.FakeGrabber,
               vcam_factory=fakes.FakeVcam)
    c = Collector()
    e.previewReady.connect(c.on_preview); e.errorOccurred.connect(c.on_error)
    e.cameraStarted.connect(c.on_started); e.cameraStopped.connect(c.on_stopped)
    e.vcamChanged.connect(c.on_vcam); e.stats.connect(c.on_stats); e.status.connect(c.on_status)
    e.start()
    wait_for.diag = lambda: (
        f"Thread laeuft: {e.isRunning()}, Kamera offen: {e._grabber is not None}, "
        f"Vorschauen: {len(c.previews)}, Statistik: {c.stats[-1:] }, gestartet: {c.started}, "
        f"Fehler: {c.errors}, vcam: {c.vcam[-2:]}, Status: {c.status[-3:]}, "
        f"fps_limit: {e.fps_limit}, preview_enabled: {e.preview_enabled}")
    yield e, c
    wait_for.diag = None
    e.shutdown()


INFO = CameraInfo("Fake", 0, 0)


def test_kamera_start_vorschau_stop(eng):
    e, c = eng
    e.open_camera(INFO)
    assert wait_for(lambda: len(c.previews) >= 3)
    assert c.started == [(640, 360)] and not c.errors
    img = c.previews[-1]
    assert not img.isNull() and (img.width(), img.height()) == (640, 360)
    assert any("l\u00e4uft" in s.lower() or "L\u00e4uft" in s for s in c.status)
    e.close_camera()
    assert wait_for(lambda: c.stopped == 1)


def test_virtuelle_kamera_an_aus_und_stop_mit_kamera(eng):
    e, c = eng
    e.open_camera(INFO)
    assert wait_for(lambda: c.started)
    e.set_vcam(True)
    assert wait_for(lambda: c.vcam and c.vcam[-1][0])
    assert c.vcam[-1] == (True, "Fake Virtual Camera")
    assert wait_for(lambda: len(e.vcam.frames) >= 3)
    assert set(e.vcam.frames) == {(360, 640, 3)}
    e.set_vcam(False)
    assert wait_for(lambda: c.vcam[-1] == (False, ""))
    n = len(e.vcam.frames)
    pump(200)
    assert len(e.vcam.frames) == n                     # nach dem Stoppen wird nichts mehr gesendet
    e.set_vcam(True)
    assert wait_for(lambda: c.vcam[-1][0])
    e.close_camera()                                   # Kamera aus -> vcam wird mitgestoppt
    assert wait_for(lambda: c.stopped == 1) and c.vcam[-1] == (False, "")


def test_vcam_ohne_kamera_und_vcam_fehler(eng):
    e, c = eng
    e.set_vcam(True)                                   # keine Kamera laeuft
    assert wait_for(lambda: c.errors and c.vcam) and c.vcam[-1][0] is False
    c.errors.clear()
    e.open_camera(INFO)
    assert wait_for(lambda: c.started)
    fakes.FakeVcam.fail = True
    e.set_vcam(True)
    assert wait_for(lambda: c.errors and c.vcam)
    assert "OBS fehlt" in c.errors[-1][1] and c.vcam[-1][0] is False
    assert wait_for(lambda: len(c.previews) >= 2)       # Vorschau laeuft weiter


def test_kamerafehler_und_modellfehler_stuerzen_nicht_ab(eng, qapp):
    e, c = eng
    fakes.FakeGrabber.fail = True
    e.open_camera(INFO)
    assert wait_for(lambda: c.errors) and "belegt" in c.errors[-1][1] and not c.started
    # Modell fehlt
    from gesichtsfilter.core.tracker import TrackerError

    def boom(gpu):
        raise TrackerError("Gesichtsmodell nicht gefunden")
    e._tracker_factory = boom
    e._tracker = None          # der Tracker vom ersten Versuch bleibt sonst bewusst erhalten
    c.errors.clear()
    fakes.FakeGrabber.fail = False
    e.open_camera(INFO)
    assert wait_for(lambda: c.errors) and "Gesichtsmodell" in c.errors[-1][1] and not c.started


def test_fps_limit(eng):
    e, c = eng
    e.fps_limit = 10                                   # Kamera liefert 30 fps
    e.preview_enabled = False
    e.open_camera(INFO)
    assert wait_for(lambda: len(c.stats) >= 3, 20000)
    fps = [f for f, _, _ in c.stats[-2:]]
    assert all(6.0 <= f <= 12.5 for f in fps), f"fps mit Limit 10: {fps}"   # nicht schneller, nicht blockiert
    assert all(t >= 0 and r > 0 for _, t, r in c.stats)
    assert max(r for _, _, r in c.stats) < 500, f"Rendern zu langsam: {c.stats}"


def test_vorschau_aus_sendet_keine_bilder(eng):
    e, c = eng
    e.preview_enabled = False
    e.open_camera(INFO)
    assert wait_for(lambda: c.started)
    pump(400)
    assert c.previews == []


def test_fehler_im_filter_beendet_thread_nicht(eng):
    e, c = eng
    fakes.FakeTracker.explode = True
    e.open_camera(INFO)
    assert wait_for(lambda: c.started and len(c.previews) >= 3)   # Rohbild wird weiter geliefert
    assert len(c.errors) == 1 and "Test-Absturz" in c.errors[0][1]  # nur EINE Meldung, kein Spam
    fakes.FakeTracker.explode = False
    n = len(c.previews)
    assert wait_for(lambda: len(c.previews) > n + 2)
    assert e.isRunning()


def test_gpu_umschalten_baut_tracker_neu(eng):
    e, c = eng
    e.open_camera(INFO)
    assert wait_for(lambda: c.started)
    first = e._tracker
    e.set_gpu(True)
    assert wait_for(lambda: e._tracker is not first and e._tracker.use_gpu is True)
    assert first.closed

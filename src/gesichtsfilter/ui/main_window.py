"""Hauptfenster (PySide6). Alle Texte deutsch.

Aufbau wie im HTML-Tool: links die Bedienung (1. Modus, 2. Bilder, 3. Marker,
4. Bewegung, 5. Augen & Mund) plus Kamera/Ausgabe/Leistung, rechts die Vorschau.
Settings/Assets sind gemeinsame Objekte mit der Engine: Aenderungen wirken sofort.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from .. import config as C
from ..core.demo import demo_assets, peanut_assets
from ..core.raster import Sprite
from ..core.settings import RigAssets, Settings
from ..engine import Engine
from ..io import profile as P
from ..io.camera import list_cameras
from ..sysutil import app_data_dir, set_low_priority
from .widgets import LabeledSlider, MarkerEditor, PreviewWidget

log = logging.getLogger(__name__)

IMG_FILTER = "Bilder (*.png *.jpg *.jpeg *.webp *.bmp);;Alle Dateien (*)"
MODES = ["Einfach: PNG folgt dem Gesicht (ohne K\u00f6rper)",
         "Ein PNG mit Markern (Kopf, Hals, K\u00f6rper)",
         "Zwei PNGs: Kopf + K\u00f6rper"]
HINTS = {
    "body": "Hals-Anker: Hier sitzt der Kopf auf dem K\u00f6rper.",
    0: "Das Bild folgt deinem Gesicht starr. Augen und Mund sitzen auf den Markern.",
    2: "Hals-Pivot: Drehpunkt des Kopfes, meist am unteren Ende des Halses im Kopf-PNG.",
    1: "Hals oben/unten: Dar\u00fcber bewegt sich alles mit dem Kopf, dazwischen wird gedehnt, "
       "darunter bleibt alles stehen.",
}


def qimage_to_sprite(img: QImage) -> Sprite:
    """QImage (z.B. aus der Zwischenablage) -> Sprite."""
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    arr = np.frombuffer(img.constBits(), np.uint8, count=img.sizeInBytes())
    arr = arr.reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()]
    bgra = cv2.cvtColor(np.ascontiguousarray(arr), cv2.COLOR_RGBA2BGRA)
    return Sprite.from_straight_bgra(bgra).limited(C.MAX_IMAGE_SIDE)


def _heading(text: str) -> QLabel:
    lb = QLabel(f"<b>{text}</b>")
    lb.setStyleSheet("margin-top:14px; font-size:14px;")
    return lb


def _note(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet("color:#a39b8f; font-size:12px;")
    return lb


class PreviewWindow(QWidget):
    """Eigenes Vorschaufenster (Doppelklick = Vollbild, Esc = zurueck/schliessen)."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gesichtsfilter \u2013 Ausgabe")
        self.view = PreviewWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self.resize(960, 540)
        self.view.doubleClicked.connect(self._toggle_full)

    def _toggle_full(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.showNormal() if self.isFullScreen() else self.close()


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine, settings: Settings, assets: RigAssets):
        super().__init__()
        self.engine, self.settings, self.assets = engine, settings, assets
        self.view = "main"
        self.src: Dict[str, Optional[dict]] = {"main": {"kind": "demo"}, "body": None}
        self.last_dir = str(Path.home())
        self._scale_auto = False
        self._cam_running = False
        self.sliders: Dict[str, LabeledSlider] = {}
        self.setWindowTitle("Gesichtsfilter \u2013 Augen & Mund auf PNG")
        self.setAcceptDrops(True)
        self.popout = PreviewWindow()

        self._build_ui()
        self._connect_engine()
        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self.paste_clipboard)

        self.load_demo(adjust_scale=False)
        self._apply_mode_ui()
        self.set_view("main")
        self._restore_session()
        self.refresh_cameras()

    # ================================================================== Aufbau
    def _build_ui(self):
        panel = QWidget()
        L = QVBoxLayout(panel)
        L.setContentsMargins(14, 12, 14, 12)

        t = QLabel("<span style='font-size:20px'><b>Augen & Mund auf PNG</b></span>")
        L.addWidget(t)
        L.addWidget(_note("Alles l\u00e4uft lokal auf deinem Rechner. Es werden keine Daten gesendet."))

        # ---- Kamera & Ausgabe
        L.addWidget(_heading("Kamera & Ausgabe"))
        row = QHBoxLayout()
        self.cmb_cam = QComboBox()
        self.cmb_cam.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.btn_refresh = QPushButton("\u21bb")
        self.btn_refresh.setToolTip("Kameras neu suchen")
        self.btn_refresh.setFixedWidth(34)
        self.btn_refresh.clicked.connect(self.refresh_cameras)
        row.addWidget(self.cmb_cam, 1)
        row.addWidget(self.btn_refresh)
        L.addLayout(row)
        self.btn_cam = QPushButton("Kamera starten")
        self.btn_cam.setObjectName("primary")
        self.btn_cam.clicked.connect(self.toggle_camera)
        L.addWidget(self.btn_cam)
        self.btn_vcam = QPushButton("Virtuelle Kamera starten")
        self.btn_vcam.setCheckable(True)
        self.btn_vcam.setEnabled(False)
        self.btn_vcam.clicked.connect(self.toggle_vcam)
        L.addWidget(self.btn_vcam)
        self.lbl_vcam = _note("Virtuelle Kamera: aus. W\u00e4hle sie danach in Zoom, Discord, OBS usw. "
                              "als \u201eOBS Virtual Camera\u201c.")
        L.addWidget(self.lbl_vcam)
        self.cmb_cam.currentIndexChanged.connect(self._camera_changed)

        # ---- 1. Modus
        L.addWidget(_heading("1. Modus"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(MODES)
        self.cmb_mode.setCurrentIndex(self.settings.mode)
        self.cmb_mode.currentIndexChanged.connect(self.on_mode_changed)
        L.addWidget(self.cmb_mode)

        # ---- 2. Bilder
        L.addWidget(_heading("2. Bilder"))
        g = QGridLayout()
        self.btn_up = QPushButton("Eigene Datei")
        self.btn_up2 = QPushButton("Eigenes K\u00f6rper-PNG")
        self.btn_pea = QPushButton("Erdnuss")
        self.btn_def = QPushButton("Demo")
        self.btn_up.clicked.connect(lambda: (self.set_view("main"), self.choose_file()))
        self.btn_up2.clicked.connect(lambda: (self.set_view("body"), self.choose_file()))
        self.btn_pea.clicked.connect(self.load_peanut)
        self.btn_def.clicked.connect(lambda: self.load_demo(adjust_scale=True))
        g.addWidget(self.btn_up, 0, 0)
        g.addWidget(self.btn_up2, 0, 1)
        g.addWidget(self.btn_pea, 1, 0)
        g.addWidget(self.btn_def, 1, 1)
        L.addLayout(g)
        self.row_views = QWidget()
        rv = QHBoxLayout(self.row_views)
        rv.setContentsMargins(0, 0, 0, 0)
        self.btn_vmain = QPushButton("Kopf bearbeiten")
        self.btn_vbody = QPushButton("K\u00f6rper bearbeiten")
        for b, v in ((self.btn_vmain, "main"), (self.btn_vbody, "body")):
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=v: self.set_view(v))
            rv.addWidget(b)
        L.addWidget(self.row_views)
        L.addWidget(_note("Auch per Drag & Drop oder Strg+V (l\u00e4dt in die gerade bearbeitete Ebene)."))

        # ---- 3. Marker
        L.addWidget(_heading("3. Marker setzen"))
        self.marker_grid = QGridLayout()
        L.addLayout(self.marker_grid)
        self.editor = MarkerEditor()
        self.editor.markerSelected.connect(self._mk_sel)
        self.editor.editFinished.connect(self._save_sidecar)
        L.addWidget(self.editor)
        self.lbl_hint = _note("")
        L.addWidget(self.lbl_hint)
        self.btn_reset_mk = QPushButton("Marker zur\u00fccksetzen")
        self.btn_reset_mk.clicked.connect(self.reset_markers)
        L.addWidget(self.btn_reset_mk)

        # ---- 4. Bewegung
        L.addWidget(_heading("4. Bewegung"))
        self.btn_rest = QPushButton("Ruhelage setzen")
        self.btn_rest.clicked.connect(self.engine.request_rest_pose)
        L.addWidget(self.btn_rest)
        self.lbl_rest = _note("Sitz gerade vor der Kamera und klicke den Knopf. "
                              "Danach z\u00e4hlt nur die Abweichung davon.")
        L.addWidget(self.lbl_rest)
        self.s_follow = self._slider("follow", "Kopf folgt (St\u00e4rke)")
        self.s_scale = self._slider("image_scale", "Bildgr\u00f6\u00dfe")
        self.s_hr = self._slider("head_ratio", "Kopf zu K\u00f6rper (Gr\u00f6\u00dfe)")
        self.chk_behind = self._check("Kopf hinter K\u00f6rper", "behind")
        for w in (self.s_follow, self.s_scale, self.s_hr, self.chk_behind):
            L.addWidget(w)

        # ---- 5. Augen & Mund
        L.addWidget(_heading("5. Augen & Mund"))
        for key, text in (("eye_scale", "Augengr\u00f6\u00dfe"), ("mouth_scale", "Mundgr\u00f6\u00dfe"),
                          ("eye_margin", "Augen-Ausschnitt (Rand)"),
                          ("mouth_margin", "Mund-Ausschnitt (Rand)"), ("feather", "Weiche Kante")):
            L.addWidget(self._slider(key, text))
        self.chk_brows = self._check("Augenbrauen mitnehmen", "brows")
        self.chk_mirror = self._check("Spiegeln", "mirror")
        L.addWidget(self.chk_brows)
        L.addWidget(self.chk_mirror)
        L.addWidget(QLabel("Hintergrund"))
        self.cmb_bg = QComboBox()
        for name, val in C.BACKGROUNDS:
            self.cmb_bg.addItem(name, val)
        self.cmb_bg.currentIndexChanged.connect(
            lambda _: setattr(self.settings, "background", self.cmb_bg.currentData()))
        L.addWidget(self.cmb_bg)

        # ---- Leistung
        L.addWidget(_heading("Leistung"))
        r = QHBoxLayout()
        r.addWidget(QLabel("Bilder pro Sekunde (Limit)"))
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(5, 60)
        self.spin_fps.setValue(C.DEFAULT_FPS)
        self.spin_fps.valueChanged.connect(lambda v: setattr(self.engine, "fps_limit", v))
        r.addWidget(self.spin_fps)
        L.addLayout(r)
        self.cmb_track = QComboBox()
        self.cmb_track.addItem("Tracking jeden Frame", 1)
        self.cmb_track.addItem("Tracking jeden 2. Frame (mit Vorhersage)", 2)
        self.cmb_track.currentIndexChanged.connect(
            lambda _: setattr(self.settings, "track_every", self.cmb_track.currentData()))
        L.addWidget(self.cmb_track)
        self.cmb_dev = QComboBox()
        self.cmb_dev.addItem("Tracking auf CPU (empfohlen)", False)
        self.cmb_dev.addItem("Tracking auf GPU (experimentell)", True)
        self.cmb_dev.currentIndexChanged.connect(lambda _: self.engine.set_gpu(self.cmb_dev.currentData()))
        L.addWidget(self.cmb_dev)
        self.chk_prio = QCheckBox("Niedrige Priorit\u00e4t (schont das Spiel)")
        self.chk_prio.setChecked(True)
        self.chk_prio.toggled.connect(set_low_priority)
        L.addWidget(self.chk_prio)
        self.chk_prev = QCheckBox("Vorschau anzeigen (aus = spart Leistung)")
        self.chk_prev.setChecked(True)
        self.chk_prev.toggled.connect(lambda _: self._update_preview_flag())
        L.addWidget(self.chk_prev)
        self.btn_pop = QPushButton("Vorschau in eigenem Fenster")
        self.btn_pop.clicked.connect(self._show_popout)
        L.addWidget(self.btn_pop)

        # ---- Profil
        L.addWidget(_heading("Profil"))
        r = QHBoxLayout()
        b1, b2 = QPushButton("Speichern \u2026"), QPushButton("Laden \u2026")
        b1.clicked.connect(self.save_profile_dialog)
        b2.clicked.connect(self.load_profile_dialog)
        r.addWidget(b1)
        r.addWidget(b2)
        L.addLayout(r)
        L.addWidget(_note("Ein Profil enth\u00e4lt alle Regler, die Marker und die Bildverweise."))
        L.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(400)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.preview = PreviewWidget()
        self.preview.doubleClicked.connect(self._show_popout)
        self.lbl_status = QLabel("Kamera starten, um zu beginnen.")
        self.lbl_status.setStyleSheet("color:#a39b8f;")
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color:#a39b8f;")
        rl.addWidget(self.preview, 1)
        rl.addWidget(self.lbl_status)
        rl.addWidget(self.lbl_stats)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(scroll)
        h.addWidget(right, 1)
        self.setCentralWidget(central)
        self.resize(1360, 820)

        # Sichtbarkeit je Modus
        self._two_widgets = [self.btn_up2, self.row_views, self.s_hr, self.chk_behind]
        self._ns_widgets = [self.btn_rest, self.lbl_rest, self.s_follow]
        for bg_i in range(self.cmb_bg.count()):
            if self.cmb_bg.itemData(bg_i) == self.settings.background:
                self.cmb_bg.setCurrentIndex(bg_i)

    def _slider(self, key: str, text: str) -> LabeledSlider:
        lo, hi, st = C.RANGES[key]
        w = LabeledSlider(text, lo, hi, st, getattr(self.settings, key))
        cast = int if key == "feather" else float
        w.changed.connect(lambda v, k=key, c=cast: setattr(self.settings, k, c(v)))
        self.sliders[key] = w
        return w

    def _check(self, text: str, key: str) -> QCheckBox:
        c = QCheckBox(text)
        c.setChecked(bool(getattr(self.settings, key)))
        c.toggled.connect(lambda v, k=key: setattr(self.settings, k, bool(v)))
        c.setProperty("settingKey", key)
        return c

    def _connect_engine(self):
        e = self.engine
        e.previewReady.connect(self._on_preview)
        e.status.connect(self.lbl_status.setText)
        e.stats.connect(self._on_stats)   # Methode eines QObject -> laeuft sicher im UI-Thread
        e.errorOccurred.connect(self._on_error)
        e.cameraStarted.connect(self._on_cam_started)
        e.cameraStopped.connect(self._on_cam_stopped)
        e.vcamChanged.connect(self._on_vcam)

    # ================================================================== Kamera
    def refresh_cameras(self):
        self.cmb_cam.blockSignals(True)
        self.cmb_cam.clear()
        try:
            cams = list_cameras()
        except Exception:
            log.exception("Kameras suchen")
            cams = []
        for c in cams:
            self.cmb_cam.addItem(c.name, c)
        if not cams:
            self.cmb_cam.addItem("Keine Kamera gefunden", None)
        self.cmb_cam.blockSignals(False)
        self.btn_cam.setEnabled(bool(cams) or self._cam_running)

    def toggle_camera(self):
        if self._cam_running:
            self.engine.close_camera()
            return
        info = self.cmb_cam.currentData()
        if info is None:
            QMessageBox.information(self, "Keine Kamera", "Es wurde keine Kamera gefunden.\n"
                                    "Schlie\u00dfe andere Programme, die sie nutzen, und klicke auf \u21bb.")
            return
        self.btn_cam.setEnabled(False)
        self.engine.open_camera(info)

    def _camera_changed(self):
        info = self.cmb_cam.currentData()
        if self._cam_running and info is not None:
            self.btn_cam.setEnabled(False)
            self.engine.open_camera(info)

    def _on_cam_started(self, w: int, h: int):
        self._cam_running = True
        self.btn_cam.setText("Kamera stoppen")
        self.btn_cam.setEnabled(True)
        self.btn_vcam.setEnabled(True)
        self.lbl_stats.setText(f"Kamera: {w}\u00d7{h}")

    def _on_cam_stopped(self):
        self._cam_running = False
        self.btn_cam.setText("Kamera starten")
        self.btn_cam.setEnabled(self.cmb_cam.currentData() is not None)
        self.btn_vcam.setEnabled(False)
        self.preview.set_image(None)
        self.popout.view.set_image(None)

    def toggle_vcam(self, checked: bool):
        self.btn_vcam.setEnabled(False)
        self.engine.set_vcam(checked)

    def _on_vcam(self, active: bool, device: str):
        self.btn_vcam.blockSignals(True)
        self.btn_vcam.setChecked(active)
        self.btn_vcam.blockSignals(False)
        self.btn_vcam.setEnabled(self._cam_running)
        self.btn_vcam.setText("Virtuelle Kamera stoppen" if active else "Virtuelle Kamera starten")
        self.lbl_vcam.setText(f"Virtuelle Kamera: <b>an</b> ({device}). W\u00e4hle sie in deinem Programm aus."
                              if active else "Virtuelle Kamera: aus.")

    def _on_error(self, title: str, text: str):
        self.btn_cam.setEnabled(self._cam_running or self.cmb_cam.currentData() is not None)
        self.btn_vcam.setEnabled(self._cam_running)
        QMessageBox.warning(self, title, text)

    def _on_stats(self, fps: float, track_ms: float, render_ms: float):
        self.lbl_stats.setText(f"{fps:.0f} fps \u00b7 Tracking {track_ms:.1f} ms \u00b7 Rendern {render_ms:.1f} ms")

    def _on_preview(self, img: QImage):
        self.preview.set_image(img)
        if self.popout.isVisible():
            self.popout.view.set_image(img)

    def _show_popout(self):
        self.popout.show()
        self.popout.raise_()
        self._update_preview_flag()

    def _update_preview_flag(self):
        self.engine.preview_enabled = self.chk_prev.isChecked() and (
            not self.isMinimized() or self.popout.isVisible())

    def changeEvent(self, e):
        super().changeEvent(e)
        if hasattr(self, "chk_prev"):
            self._update_preview_flag()

    # ================================================================== Modus & Marker
    def _idxs(self) -> List[int]:
        return C.MARKER_INDICES["body"] if self.view == "body" else C.MARKER_INDICES[self.settings.mode]

    def _mdef(self, i: int):
        if self.view == "body":
            return C.BODY_ANCHOR_DEF
        if self.settings.mode == 2 and i == 4:
            return C.PIVOT_DEF
        return C.MARKER_DEFS[i]

    def on_mode_changed(self, idx: int):
        was_two = self.settings.mode == 2
        self.settings.mode = idx
        self._apply_mode_ui()
        # Demo passt sich dem Modus an (ein Bild <-> Kopf + Koerper)
        if (idx == 2) != was_two and self.src["main"] and self.src["main"]["kind"] == "demo":
            self.load_demo(adjust_scale=True)
        self.set_view("main")

    def _apply_mode_ui(self):
        m = self.settings.mode
        for w in self._two_widgets:
            w.setVisible(m == 2)
        for w in self._ns_widgets:
            w.setVisible(m != 0)
        self.btn_up.setText("Eigenes Kopf-PNG" if m == 2 else "Eigene Datei")
        if m != 2 and self.view == "body":
            self.view = "main"

    def set_view(self, view: str):
        self.view = view if (view == "main" or self.settings.mode == 2) else "main"
        self.btn_vmain.setChecked(self.view == "main")
        self.btn_vbody.setChecked(self.view == "body")
        idxs = self._idxs()
        self.editor.current = idxs[0]
        while self.marker_grid.count():
            it = self.marker_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._mk_buttons = {}
        for n, i in enumerate(idxs):
            name, col, _ = self._mdef(i)
            b = QPushButton(name)
            b.setCheckable(True)
            b.setStyleSheet(f"color:{col}; font-weight:bold;")
            b.clicked.connect(lambda _=False, i=i: self._mk_click(i))
            self.marker_grid.addWidget(b, n // 3, n % 3)
            self._mk_buttons[i] = b
        self.lbl_hint.setText(HINTS["body"] if self.view == "body" else HINTS[self.settings.mode])
        self.refresh_editor()
        self._mk_sel(self.editor.current)

    def _mk_click(self, i: int):
        self.editor.set_current(i)
        self._mk_sel(i)

    def _mk_sel(self, i: int):
        for k, b in getattr(self, "_mk_buttons", {}).items():
            b.setChecked(k == i)

    def refresh_editor(self):
        main = self.view == "main"
        sprite = self.assets.head if main else self.assets.body
        markers = self.assets.head_markers if main else self.assets.body_marker
        idxs = self._idxs()
        guides = [3, 4] if (main and self.settings.mode == 1) else []
        self.editor.set_content(sprite, markers, idxs, {i: self._mdef(i) for i in idxs}, guides)

    def reset_markers(self):
        if self.view == "main":
            self.assets.head_markers = [m[:] for m in C.DEFAULT_MARKERS]
        else:
            self.assets.body_marker = [m[:] for m in C.DEFAULT_BODY_MARKER]
        self.refresh_editor()
        self._save_sidecar()

    # ================================================================== Bilder
    def _set_layer(self, view: str, sprite: Sprite, markers: List[List[float]], src: dict):
        if view == "main":
            self.assets.head_markers = markers
            self.assets.head = sprite
        else:
            self.assets.body_marker = markers
            self.assets.body = sprite
        self.src[view] = src
        if self.view == view:
            self.refresh_editor()

    def load_file(self, path: str, view: Optional[str] = None):
        view = view or self.view
        try:
            sprite = Sprite.from_file(path)
        except ValueError as e:
            QMessageBox.warning(self, "Bild laden", str(e))
            return
        self.last_dir = str(Path(path).parent)
        n = (5, 5) if view == "main" else (1, 1)
        default = C.DEFAULT_MARKERS if view == "main" else C.DEFAULT_BODY_MARKER
        markers = P.load_sidecar(path, *n) or [m[:] for m in default]
        self._set_layer(view, sprite, markers, {"kind": "file", "path": str(path)})

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Bild w\u00e4hlen", self.last_dir, IMG_FILTER)
        if path:
            self.load_file(path)

    def load_peanut(self):
        self.set_view("main")
        a = peanut_assets()
        self._set_layer("main", a.head, a.head_markers, {"kind": "peanut"})

    def load_demo(self, adjust_scale: bool = True):
        two = self.settings.mode == 2
        a = demo_assets(two)
        self._set_layer("main", a.head, a.head_markers, {"kind": "demo"})
        if two:
            self._set_layer("body", a.body, a.body_marker, {"kind": "demo"})
        if adjust_scale:
            # Im Zwei-PNG-Modus ist 1.0 fuer das Demo-Bild viel zu gross (Formel aus dem HTML-Tool)
            cur = self.settings.image_scale
            if two and abs(cur - 1.0) < 1e-6:
                self._set_slider("image_scale", 0.5)
                self._scale_auto = True
            elif not two and self._scale_auto and abs(cur - 0.5) < 1e-6:
                self._set_slider("image_scale", 1.0)
            if not two:
                self._scale_auto = False

    def _load_demo_layer(self, view: str):
        """Laedt nur die Kopf- ODER Koerper-Ebene des Demo-Bildes."""
        if view == "main":
            a = demo_assets(self.settings.mode == 2)
            self._set_layer("main", a.head, a.head_markers, {"kind": "demo"})
        else:
            a = demo_assets(True)
            self._set_layer("body", a.body, a.body_marker, {"kind": "demo"})

    def _set_slider(self, key: str, v: float):
        self.sliders[key].set_value(v)
        setattr(self.settings, key, v)

    def paste_clipboard(self):
        img = QGuiApplication.clipboard().image()
        if img.isNull():
            return
        sp = qimage_to_sprite(img)
        main = self.view == "main"
        self._set_layer(self.view, sp, [m[:] for m in (C.DEFAULT_MARKERS if main else C.DEFAULT_BODY_MARKER)],
                        {"kind": "clipboard"})

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.load_file(urls[0])
        elif e.mimeData().hasImage():
            self.paste_clipboard()

    def _save_sidecar(self):
        s = self.src.get(self.view)
        if s and s["kind"] == "file":
            P.save_sidecar(s["path"], self.assets.head_markers if self.view == "main"
                           else self.assets.body_marker)

    # ================================================================== Profile
    def _perf(self) -> dict:
        return {"fps": self.spin_fps.value(), "gpu": bool(self.cmb_dev.currentData()),
                "low_priority": self.chk_prio.isChecked(), "preview": self.chk_prev.isChecked()}

    def _export_clipboard_layers(self, profile_path: Path):
        """Aus der Zwischenablage eingefuegte Bilder neben dem Profil als PNG ablegen."""
        for view, suffix in (("main", "_kopf"), ("body", "_koerper")):
            s = self.src.get(view)
            sprite = self.assets.head if view == "main" else self.assets.body
            if s and s["kind"] == "clipboard" and sprite is not None:
                p = profile_path.with_name(profile_path.stem + suffix + ".png")
                sprite.save_png(p)
                self.src[view] = {"kind": "file", "path": str(p)}

    def save_profile_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Profil speichern", self.last_dir, "Profil (*.json)")
        if not path:
            return
        path = Path(path if path.lower().endswith(".json") else path + ".json")
        try:
            self._write_profile(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Profil speichern", f"Konnte nicht gespeichert werden:\n{e}")

    def _write_profile(self, path: Path):
        self._export_clipboard_layers(path)
        P.save_profile(path, self.settings, self._perf(), self.src["main"], self.assets.head_markers,
                       self.src.get("body") if self.settings.mode == 2 or self.assets.body else None,
                       self.assets.body_marker)

    def load_profile_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Profil laden", self.last_dir, "Profil (*.json)")
        if not path:
            return
        try:
            self.apply_profile(P.load_profile(path))
        except ValueError as e:
            QMessageBox.warning(self, "Profil laden", str(e))

    def apply_profile(self, d: dict):
        # 1) Einstellungen in das gemeinsame Objekt uebernehmen (Identitaet bleibt erhalten)
        new = Settings.from_dict(d["settings"])
        for k in new.__dataclass_fields__:
            setattr(self.settings, k, getattr(new, k))
        self._sync_controls()
        self._apply_mode_ui()
        # 2) Leistungsoptionen
        perf = d.get("performance", {})
        if "fps" in perf:
            self.spin_fps.setValue(int(perf["fps"]))
        if "gpu" in perf:
            self.cmb_dev.setCurrentIndex(1 if perf["gpu"] else 0)
        if "low_priority" in perf:
            self.chk_prio.setChecked(bool(perf["low_priority"]))
        if "preview" in perf:
            self.chk_prev.setChecked(bool(perf["preview"]))
        # 3) Bilder
        missing = []
        for view, ref_key, mk_key in (("main", "head", "head_markers"), ("body", "body", "body_marker")):
            ref = d.get(ref_key)
            if ref is None:
                continue
            if ref["kind"] == "demo":
                self._load_demo_layer(view)   # nur diese Ebene, die andere bleibt unberuehrt
            elif ref["kind"] == "peanut":
                a = peanut_assets()
                self._set_layer("main", a.head, a.head_markers, {"kind": "peanut"})
            else:
                try:
                    sp = Sprite.from_file(ref["path"])
                    self._set_layer(view, sp, [m[:] for m in (C.DEFAULT_MARKERS if view == "main"
                                                              else C.DEFAULT_BODY_MARKER)], ref)
                except ValueError:
                    missing.append(ref["path"])
                    continue
            if d.get(mk_key):
                if view == "main":
                    self.assets.head_markers = d[mk_key]
                else:
                    self.assets.body_marker = d[mk_key]
        self.set_view("main")
        if missing:
            QMessageBox.warning(self, "Profil laden", "Diese Bilddateien fehlen oder sind nicht lesbar:\n"
                                + "\n".join(missing))

    def _sync_controls(self):
        for key, sl in self.sliders.items():
            sl.set_value(getattr(self.settings, key))
        for c in (self.chk_behind, self.chk_brows, self.chk_mirror):
            c.blockSignals(True)
            c.setChecked(bool(getattr(self.settings, c.property("settingKey"))))
            c.blockSignals(False)
        self.cmb_mode.blockSignals(True)
        self.cmb_mode.setCurrentIndex(self.settings.mode)
        self.cmb_mode.blockSignals(False)
        for combo, val in ((self.cmb_bg, self.settings.background), (self.cmb_track, self.settings.track_every)):
            combo.blockSignals(True)
            for i in range(combo.count()):
                if combo.itemData(i) == val:
                    combo.setCurrentIndex(i)
            combo.blockSignals(False)

    # ================================================================== Sitzung
    def _session_file(self) -> Path:
        return app_data_dir() / "zuletzt.json"

    def _restore_session(self):
        f = self._session_file()
        if f.exists():
            try:
                self.apply_profile(P.load_profile(f))
            except Exception:
                log.exception("Letzte Sitzung konnte nicht geladen werden")

    def closeEvent(self, e):
        try:
            self._write_profile(self._session_file())
        except Exception:
            log.exception("Sitzung speichern")
        self.popout.close()
        self.engine.shutdown()
        super().closeEvent(e)

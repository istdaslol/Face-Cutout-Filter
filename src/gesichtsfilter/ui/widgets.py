"""Eigene Widgets: Regler mit Wert, Marker-Editor (ziehbare Marker), Vorschau."""
import math
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap)
from PySide6.QtWidgets import (QComboBox, QLabel, QListView, QSlider, QStyledItemDelegate, QVBoxLayout,
                               QWidget)

from ..core.raster import Sprite

ACCENT = "#ffb347"


class StyledCombo(QComboBox):
    """Dropdown, dessen Liste vom Stylesheet gestaltet wird (lesbarer Hover/Auswahl-Eintrag).

    Ohne eigene Listenansicht und Delegate ignoriert die Popup-Liste die ::item-Regeln des
    Stylesheets; der Eintrag unter der Maus wurde dann dunkel auf dunkel gezeichnet.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView(self))
        self.setItemDelegate(QStyledItemDelegate(self))


class LabeledSlider(QWidget):
    """Regler mit Beschriftung und Wertanzeige; arbeitet mit echten Zahlen (float)."""
    changed = Signal(float)

    def __init__(self, text: str, lo: float, hi: float, step: float, value: float, parent=None):
        super().__init__(parent)
        self._text, self._lo, self._step = text, lo, step
        self._decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
        self._s = QSlider(Qt.Orientation.Horizontal)
        self._s.setRange(0, int(round((hi - lo) / step)))
        self._lbl = QLabel()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._lbl)
        lay.addWidget(self._s)
        self.set_value(value)
        self._s.valueChanged.connect(self._on_slider)

    def _val(self) -> float:
        return self._lo + self._s.value() * self._step

    def _refresh(self):
        self._lbl.setText(f"{self._text}: <b>{self._val():.{self._decimals}f}</b>")

    def _on_slider(self, _):
        self._refresh()
        self.changed.emit(self._val())

    def set_value(self, v: float):
        """Setzt den Wert ohne Signal."""
        self._s.blockSignals(True)
        self._s.setValue(int(round((v - self._lo) / self._step)))
        self._s.blockSignals(False)
        self._refresh()

    def value(self) -> float:
        return self._val()


def _checker(size: int = 16) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor("#3a3631"))
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QColor("#2f2c28"))
    p.fillRect(size, size, size, size, QColor("#2f2c28"))
    p.end()
    return pm


def sprite_to_qimage(sp: Sprite) -> QImage:
    """Vormultipliziertes BGRA entspricht exakt Format_ARGB32_Premultiplied (little endian)."""
    return QImage(sp.pm.data, sp.w, sp.h, sp.w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()


class MarkerEditor(QWidget):
    """Zeigt ein Bild mit ziehbaren Markern. Marker sind relative Koordinaten (0..1).

    Verhalten wie im HTML-Tool: Klick/Ziehen nahe an einem Marker (<24 px)
    waehlt und verschiebt ihn, Klick ins Leere setzt den aktuellen Marker dorthin.
    """
    markersEdited = Signal()            # Marker wurden veraendert (bei jeder Bewegung)
    editFinished = Signal()             # Maus losgelassen (gut zum Speichern)
    markerSelected = Signal(int)

    RADIUS = 13
    PICK = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img: Optional[QImage] = None
        self._markers: List[List[float]] = []
        self._defs = {}                  # idx -> (name, color, letter)
        self._visible: Sequence[int] = []
        self._guides: Sequence[int] = []
        self.current = 0
        self._drag = -1
        self._bg = _checker()
        self.setMinimumHeight(70)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # -------------------------------------------------------------- Daten
    def set_content(self, sprite: Optional[Sprite], markers: List[List[float]], visible: Sequence[int],
                    defs: dict, guides: Sequence[int] = ()):
        self._img = sprite_to_qimage(sprite) if sprite is not None else None
        self._markers, self._visible, self._defs, self._guides = markers, list(visible), defs, list(guides)
        if self.current not in self._visible and self._visible:
            self.current = self._visible[0]
        self._fit()
        self.update()

    def set_current(self, i: int):
        self.current = i
        self.update()

    def _fit(self):
        w = max(self.width(), 100)
        h = 70 if self._img is None else max(40, round(w * self._img.height() / self._img.width()))
        if self.minimumHeight() != h or self.maximumHeight() != h:
            self.setFixedHeight(h)

    def resizeEvent(self, e):
        self._fit()
        super().resizeEvent(e)

    # -------------------------------------------------------------- Zeichnen
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.rect()
        p.drawTiledPixmap(r, self._bg)
        if self._img is None:
            p.setPen(QColor("#a39b8f"))
            p.drawText(10, 38, "Noch kein Bild geladen.")
            return
        p.drawImage(QRectF(r), self._img)
        w, h = r.width(), r.height()
        if self._guides and len(self._markers) > max(self._guides):   # Hals oben/unten
            pen = QPen(QColor("#ffd166"), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            for i in self._guides:
                y = self._markers[i][1] * h
                p.drawLine(QPointF(0, y), QPointF(w, y))
        f = QFont()
        f.setBold(True)
        f.setPointSize(8)
        p.setFont(f)
        for i in self._visible:
            if i >= len(self._markers):
                continue
            name, col, letter = self._defs[i]
            c = QPointF(self._markers[i][0] * w, self._markers[i][1] * h)
            fill = QColor(col)
            fill.setAlpha(0x99)
            p.setBrush(QBrush(fill))
            p.setPen(QPen(QColor(col), 3 if i != self.current else 4))
            p.drawEllipse(c, self.RADIUS, self.RADIUS)
            p.setPen(QColor("#000"))
            p.drawText(QRectF(c.x() - 12, c.y() - 12, 24, 24), Qt.AlignmentFlag.AlignCenter, letter)

    # -------------------------------------------------------------- Maus
    def _norm(self, pos) -> Tuple[float, float]:
        return (min(1.0, max(0.0, pos.x() / max(1, self.width()))),
                min(1.0, max(0.0, pos.y() / max(1, self.height()))))

    def mousePressEvent(self, e):
        if self._img is None or e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position()
        p = self._norm(pos)
        best, bd = -1, float(self.PICK)
        for i in self._visible:
            d = math.hypot(self._markers[i][0] * self.width() - pos.x(),
                           self._markers[i][1] * self.height() - pos.y())
            if d < bd:
                bd, best = d, i
        self._drag = best if best >= 0 else self.current
        if best >= 0 and best != self.current:
            self.current = best
            self.markerSelected.emit(best)
        self._markers[self._drag][0], self._markers[self._drag][1] = p
        self.markersEdited.emit()
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag >= 0:
            self._markers[self._drag][0], self._markers[self._drag][1] = self._norm(e.position())
            self.markersEdited.emit()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag >= 0:
            self._drag = -1
            self.editFinished.emit()


class PreviewWidget(QWidget):
    """Zeigt das zuletzt gelieferte Bild, seitenverhaeltnisrichtig, auf schwarzem Grund."""
    doubleClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img: Optional[QImage] = None
        self.placeholder = "Kamera starten, um zu beginnen."
        self.setMinimumSize(320, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def set_image(self, img: Optional[QImage]):
        self._img = img
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000"))
        if self._img is None:
            p.setPen(QColor("#a39b8f"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = self._img.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width() - s.width()) // 2, (self.height() - s.height()) // 2
        p.drawImage(QRectF(x, y, s.width(), s.height()), self._img)

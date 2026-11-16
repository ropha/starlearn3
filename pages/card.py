from __future__ import annotations
import math
import time
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath,
    QPixmap, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QWidget
ROOT = Path(__file__).resolve().parent
CATS = ROOT.parent / "assets" / "cats"
CARD_SHOW_MS = 6000
IN_MS = 640
RAYS_MS_TURN = 26000
REVEAL_MS = 560
RAINBOW = (
    (0.000, 255, 96, 96),
    (0.125, 255, 176, 72),
    (0.250, 255, 236, 96),
    (0.375, 132, 236, 128),
    (0.500, 96, 208, 255),
    (0.625, 132, 152, 255),
    (0.750, 208, 132, 255),
    (0.875, 255, 132, 184),
    (1.000, 255, 96, 96),
)
def _ease(u: float) -> float:
    return 1.0 - (1.0 - u) ** 3
class CardOverlay(QWidget):
    hidden_done = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()
        self._pix = QPixmap()
        self._t0 = 0.0
        self._angle = 0.0
        self._scale, self._rot, self._fade, self._reveal = 0.72, -1.5, 0.0, 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
    def show_card(self, node: str, tier: str) -> None:
        path = CATS / str(node) / f"{tier}-v1.png"
        if not path.exists():
            return
        self._pix = QPixmap(str(path))
        self._t0 = time.monotonic()
        self._angle = 0.0
        self._scale, self._rot, self._fade, self._reveal = 0.72, -1.5, 0.0, 0.0
        self._timer.start()
        self.show()
        self.raise_()
    def _tick(self) -> None:
        t = (time.monotonic() - self._t0) * 1000
        self._angle = (t / RAYS_MS_TURN * 360) % 360
        if t <= IN_MS:
            u = t / IN_MS
            if u < 0.62:
                e = _ease(u / 0.62)
                self._scale = 0.72 + 0.32 * e
                self._rot = -1.5 + 1.9 * e
            else:
                e = _ease((u - 0.62) / 0.38)
                self._scale = 1.04 - 0.04 * e
                self._rot = 0.4 - 0.4 * e
            self._fade = min(1.0, u / 0.31)
            self._reveal = _ease(min(1.0, t / REVEAL_MS))
        else:
            self._scale, self._rot, self._fade, self._reveal = 1.0, 0.0, 1.0, 1.0
        if t >= CARD_SHOW_MS:
            self._timer.stop()
            self.hide()
            self.hidden_done.emit()
            return
        self.update()
    def paintEvent(self, _ev) -> None:
        if self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        unit = min(w, h)
        cx, cy = w / 2, h * 0.46
        fade = self._fade
        p.setPen(Qt.NoPen)
        g = QRadialGradient(QPointF(cx, cy), max(w, h) * 0.72)
        g.setColorAt(0.00, QColor(255, 238, 196, int(56 * fade)))
        g.setColorAt(0.34, QColor(130, 90, 30, int(46 * fade)))
        g.setColorAt(0.68, QColor(10, 7, 4, int(232 * fade)))
        g.setColorAt(1.00, QColor(10, 7, 4, int(222 * fade)))
        p.setBrush(g)
        p.drawRect(self.rect())
        R = math.hypot(w, h) * 0.62
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)
        for i in range(24):
            a0 = i * 15.0
            pts = [QPointF(0, 0)]
            for k in range(3):
                a = math.radians(a0 + 2.6 * k / 2)
                pts.append(QPointF(R * math.cos(a), R * math.sin(a)))
            tint = (i % 8) / 8.0
            rc = 255
            gc = int(214 + 30 * math.sin(tint * math.pi))
            bc = int(150 + 60 * math.cos(tint * math.pi))
            rg = QRadialGradient(QPointF(0, 0), R)
            rg.setColorAt(0.00, QColor(rc, gc, bc, int(132 * fade)))
            rg.setColorAt(0.26, QColor(rc, gc, bc, int(64 * fade)))
            rg.setColorAt(0.58, QColor(rc, gc, bc, 0))
            p.setBrush(rg)
            p.drawPolygon(QPolygonF(pts))
        p.restore()
        pw0 = self._pix.width() * self._scale
        ph0 = self._pix.height() * self._scale
        fit = min(w * 0.78 / pw0, h * 0.86 / ph0, 1.0)
        pw, ph = pw0 * fit, ph0 * fit
        ring_alpha = (0.92 if self._reveal < 1.0 else 0.20) * fade
        if ring_alpha > 0.01:
            cg = QConicalGradient(QPointF(0, 0), self._angle * 1.6)
            for pos, r, gc_, b in RAINBOW:
                cg.setColorAt(pos, QColor(r, gc_, b, int(198 * ring_alpha)))
            p.save()
            p.translate(cx, cy)
            rr = max(pw, ph) * 0.60
            ring = QPainterPath()
            ring.addEllipse(QRectF(-rr, -rr, rr * 2, rr * 2))
            inner = max(pw, ph) * 0.40
            ring.addEllipse(QRectF(-inner, -inner, inner * 2, inner * 2))
            p.setClipPath(ring)
            p.setBrush(cg)
            p.drawRect(QRectF(-rr, -rr, rr * 2, rr * 2))
            p.setClipping(False)
            p.restore()
        sg = QRadialGradient(QPointF(cx, cy), unit * 0.46)
        sg.setColorAt(0.00, QColor(255, 232, 178, int(96 * fade)))
        sg.setColorAt(0.40, QColor(255, 205, 120, int(30 * fade)))
        sg.setColorAt(1.00, QColor(255, 205, 120, 0))
        p.setBrush(sg)
        p.drawEllipse(QRectF(cx - unit * 0.46, cy - unit * 0.46, unit * 0.92, unit * 0.92))
        p.save()
        p.translate(cx, cy)
        p.rotate(self._rot)
        sh = QRadialGradient(QPointF(0, ph * 0.46), max(pw, ph) * 0.6)
        sh.setColorAt(0, QColor(0, 0, 0, int(130 * fade)))
        sh.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(sh)
        p.drawEllipse(QRectF(-pw * 0.55, ph * 0.30, pw * 1.1, ph * 0.42))
        hg = QRadialGradient(QPointF(0, 0), max(pw, ph) * 0.75)
        hg.setColorAt(0, QColor(255, 210, 140, int(120 * fade)))
        hg.setColorAt(1, QColor(255, 210, 140, 0))
        p.setBrush(hg)
        p.drawEllipse(QRectF(-pw * 0.8, -ph * 0.8, pw * 1.6, ph * 1.6))
        rev = self._reveal
        card = QRectF(-pw / 2, -ph / 2, pw, ph)
        half = max(1.0, pw / 2 * rev)
        if rev < 0.999:
            p.setClipRect(QRectF(-half, -ph / 2 - 2, half * 2, ph + 4))
        p.setOpacity(fade)
        p.drawPixmap(card, self._pix, QRectF(self._pix.rect()))
        p.setOpacity(1.0)
        if rev < 0.999:
            p.setClipping(False)
            bw = max(10.0, 24 * unit / 900.0)
            for edge in (-half, half):
                lg = QLinearGradient(edge - bw / 2, 0, edge + bw / 2, 0)
                for pos, r, gc_, b in RAINBOW:
                    lg.setColorAt(pos, QColor(r, gc_, b, int(224 * fade)))
                p.fillRect(QRectF(edge - bw / 2, -ph / 2, bw, ph), lg)
        p.restore()

from __future__ import annotations
import math
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget
import theme
from pages.card import CATS
from pages.hud import P0, hud_scale
from pages.widgets import BrandMark, NextOrb
CARD_P = 380.0
RATIO = 1.3
GAP_P = 34.0
PAD_BOTTOM_P = 96.0
PAD_X_P = 14.0
PAD_TOP_P = 30.0
LIFT_P = 8.0
MONTHS = [f"{m:02d}" for m in range(1, 13)]
_SRC: dict[str, QPixmap] = {}
_PHOTO: dict[tuple, QPixmap] = {}
def _photo(path: str, w: int, h: int, dpr: float) -> QPixmap:
    key = (path, w, h, round(dpr, 2))
    pm = _PHOTO.get(key)
    if pm is None:
        if len(_PHOTO) > 48:
            _PHOTO.clear()
        src = _source(Path(path))
        pm = QPixmap(max(int(w * dpr), 1), max(int(h * dpr), 1))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(theme.BG))
        if not src.isNull():
            p = QPainter(pm)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.drawPixmap(QRectF(0, 0, w, h), src, QRectF(src.rect()))
            p.end()
        _PHOTO[key] = pm
    return pm
def ym(at: float) -> str:
    d = datetime.fromtimestamp(at)
    return f"{d.year}-{MONTHS[d.month - 1]}"
def _source(path: Path) -> QPixmap:
    key = str(path)
    if key not in _SRC:
        _SRC[key] = QPixmap(key) if path.exists() else QPixmap()
    return _SRC[key]
class _Track(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.P = 1.0
        self.step = 0.0
        self.items: list[dict] = []
    def glow_rect(self) -> QRectF:
        r = QRectF()
        u = self.P
        for it in self.items:
            if it["is_new"]:
                r = r.united(QRectF(it["x"] - 13 * u, it["y"] - 13 * u,
                                    it["w"] + 26 * u, it["h"] + 26 * u))
        return r
    def paintEvent(self, _ev) -> None:
        if not self.items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        u = self.P
        p.setPen(QPen(QColor(58, 46, 34, int(255 * 0.24)), max(3 * u, 1)))
        for it in self.items[:-1]:
            y = it["y"] + it["h"] + PAD_BOTTOM_P * u - 78 * u
            x0 = it["x"] + it["w"] / 2
            p.drawLine(QPointF(x0, y), QPointF(x0 + self.step, y))
        breath = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(time.monotonic() * 2 * math.pi / 3))
        for it in self.items:
            if not it["is_new"]:
                continue
            x, y, w, h = it["x"], it["y"], it["w"], it["h"]
            glow = QRadialGradient(QPointF(x + w / 2, y + h * 0.32), w * 0.72)
            glow.setColorAt(0.00, QColor(122, 206, 255, int(217 * breath)))
            glow.setColorAt(0.46, QColor(70, 165, 255, int(102 * breath)))
            glow.setColorAt(1.00, QColor(70, 165, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(
                QRectF(x - 13 * u, y - 13 * u, w + 26 * u, h + 26 * u), 30 * u, 30 * u
            )
class CatCard(QWidget):
    def __init__(self, card: dict, is_new: bool, show_month: bool, P: float, last: bool, parent=None):
        super().__init__(parent)
        self.P = P
        self.is_new = is_new
        self.show_month = show_month
        self.last = last
        node, tier = str(card.get("node") or ""), str(card.get("tier") or "初识")
        self._path = str(CATS / node / f"{tier}-v1.png")
        ts = float(card.get("at") or 0) / 1000
        try:
            self.month = ym(ts) if ts else ""
        except (OSError, ValueError, OverflowError):
            self.month = ""
        self._w = int(CARD_P * P)
        self._h = int(CARD_P * RATIO * P)
        self._pad_x = int(PAD_X_P * P)
        self._pad_top = int(PAD_TOP_P * P)
        self.setFixedSize(
            self._w + int(GAP_P * P) + 2 * self._pad_x,
            self._h + int(PAD_BOTTOM_P * P) + self._pad_top,
        )
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._t0 = time.monotonic()
        self._sweep = QTimer(self)
        self._sweep.setInterval(16)
        self._sweep.timeout.connect(self._sweep_tick)
        if is_new:
            self._sweep.start()
    def _sweep_tick(self) -> None:
        self.update()
        if (time.monotonic() - self._t0) * 1000 > 1300:
            self._sweep.stop()
    def enterEvent(self, ev) -> None:
        self._hover = True
        self.update()
        super().enterEvent(ev)
    def leaveEvent(self, ev) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(ev)
    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        u = self.P
        w, h = self._w, self._h
        lift = int(LIFT_P * u) if self._hover else 0
        p.save()
        p.translate(self._pad_x, self._pad_top - lift)
        p.setPen(Qt.NoPen)
        layers = ((12, 0, 34), (18, 6, 18), (26, 12, 10)) if self._hover \
            else ((6, 0, 26), (10, 4, 12), (14, 9, 6))
        for dy, spread, alpha in layers:
            p.setBrush(QColor(110, 80, 30, alpha))
            p.drawRoundedRect(
                QRectF(-spread * u, (dy - spread) * u, w + 2 * spread * u, h + 2 * spread * u),
                (18 + spread) * u, (18 + spread) * u,
            )
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 18 * u, 18 * u)
        p.setClipPath(clip)
        p.drawPixmap(QPointF(0, 0), _photo(self._path, w, h, self.devicePixelRatioF()))
        if self.is_new:
            ov = QLinearGradient(0, 0, 0, h)
            ov.setColorAt(0.00, QColor(198, 235, 255, int(255 * 0.50)))
            ov.setColorAt(0.42, QColor(198, 235, 255, int(255 * 0.07)))
            ov.setColorAt(0.62, QColor(198, 235, 255, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
            p.setBrush(ov)
            p.drawRect(QRectF(0, 0, w, h))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            t = (time.monotonic() - self._t0) * 1000 - 300
            if 0 <= t <= 900:
                prog = 1 - (1 - t / 900) ** 2
                bw = w * 0.55
                left = -w * 0.9 + prog * w * 2.3
                band = QLinearGradient(left, 0, left + bw, h)
                band.setColorAt(0.0, QColor(235, 250, 255, 0))
                band.setColorAt(0.5, QColor(235, 250, 255, 178))
                band.setColorAt(1.0, QColor(235, 250, 255, 0))
                p.setBrush(band)
                p.save()
                p.translate(left + bw / 2, h * 0.5)
                p.rotate(14)
                p.translate(-(left + bw / 2), -h * 0.5)
                p.drawRect(QRectF(left, -h * 0.6, bw, h * 2.2))
                p.restore()
        p.setClipping(False)
        p.restore()
        cx = self._pad_x + w / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(58, 46, 34, int(255 * 0.34)))
        p.drawEllipse(QRectF(cx - 5.5 * u, self.height() - 74 * u - 11 * u, 11 * u, 11 * u))
        if self.show_month and self.month:
            f = QFont(theme.FONT)
            f.setPixelSize(max(int(16 * u), 9))
            f.setBold(True)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 16 * u * 0.05)
            p.setFont(f)
            p.setPen(QColor(58, 46, 34, int(255 * 0.52)))
            p.drawText(QRectF(self._pad_x, self.height() - 44 * u - 16 * u, w, 16 * u),
                       Qt.AlignCenter, self.month)
class SessionEndPage(QWidget):
    continued = Signal()
    ended = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[dict] = []
        self._target = 0.0
        self._drag = False
        self._sx = 0.0
        self._start_scroll = 0.0
        self._last_x = 0.0
        self._last_t = 0.0
        self._vel = 0.0
        self._end_arm = False
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(BrandMark(27))
        self.brand = QLabel("  Ai数学老师")
        self.brand.setObjectName("brand")
        top.addWidget(self.brand)
        top.addStretch(1)
        self.btn_x = QPushButton("×")
        self.btn_x.setObjectName("ghost")
        self.btn_x.setCursor(Qt.PointingHandCursor)
        self.btn_x.clicked.connect(self._on_x)
        top.addWidget(self.btn_x)
        self.top = QWidget(self)
        self.top.setLayout(top)
        self._end_timer = QTimer(self)
        self._end_timer.setSingleShot(True)
        self._end_timer.timeout.connect(self._disarm_end)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollBar:horizontal{height:0px;background:transparent}")
        self.track = _Track()
        self.scroll.setWidget(self.track)
        self.scroll.viewport().installEventFilter(self)
        self.next = NextOrb(int(128 * P0), self)
        self.next.clicked.connect(self.continued.emit)
        self._anim = QTimer(self)
        self._anim.setInterval(7)
        self._anim.setTimerType(Qt.PreciseTimer)
        self._anim.timeout.connect(self._tick)
        self._last_tick = time.monotonic()
        self._breathe = QTimer(self)
        self._breathe.setInterval(40)
        self._breathe.timeout.connect(self._breathe_tick)
    def _breathe_tick(self) -> None:
        r = self.track.glow_rect()
        if not r.isNull():
            self.track.update(r.toAlignedRect())
    def _on_x(self) -> None:
        if self._end_arm:
            self._disarm_end()
            self.ended.emit()
            return
        self._end_arm = True
        self.btn_x.setText("结束?")
        self._end_timer.start(3000)
    def _disarm_end(self) -> None:
        self._end_timer.stop()
        if not self._end_arm:
            return
        self._end_arm = False
        self.btn_x.setText("×")
    def eventFilter(self, obj, ev) -> bool:
        if obj is self.scroll.viewport():
            bar = self.scroll.horizontalScrollBar()
            if ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._drag = True
                self._sx = ev.position().x()
                self._start_scroll = bar.value()
                self._last_x = ev.position().x()
                self._last_t = time.monotonic()
                self._vel = 0.0
                self._anim.stop()
                self.scroll.setCursor(Qt.ClosedHandCursor)
                return True
            if ev.type() == QEvent.MouseMove and self._drag:
                now = time.monotonic()
                dx = ev.position().x() - self._last_x
                dt = max(8, (now - self._last_t) * 1000)
                self._vel = dx / dt * 16
                self._last_x = ev.position().x()
                self._last_t = now
                v = self._start_scroll - (ev.position().x() - self._sx)
                bar.setValue(int(max(0, min(bar.maximum(), v))))
                self._target = bar.value()
                return True
            if ev.type() == QEvent.MouseButtonRelease and self._drag:
                self._drag = False
                self.scroll.setCursor(Qt.OpenHandCursor)
                if abs(self._vel) > 0.5:
                    self._target = max(0, min(bar.maximum(), bar.value() - self._vel * 12))
                    self._start_anim()
                return True
        return super().eventFilter(obj, ev)
    def wheelEvent(self, ev) -> None:
        bar = self.scroll.horizontalScrollBar()
        if abs(ev.angleDelta().y()) <= abs(ev.angleDelta().x()):
            return
        self._target = max(0, min(bar.maximum(), self._target + ev.angleDelta().y() * 1.1))
        self._start_anim()
    def _start_anim(self) -> None:
        self._last_tick = time.monotonic()
        self._breathe.stop()
        if not self._anim.isActive():
            self._anim.start()
    def _tick(self) -> None:
        now = time.monotonic()
        dt = max(0.001, min(0.05, now - self._last_tick))
        self._last_tick = now
        bar = self.scroll.horizontalScrollBar()
        d = self._target - bar.value()
        if abs(d) < 1.0:
            bar.setValue(int(round(self._target)))
            self._anim.stop()
            if any(it["is_new"] for it in self.track.items):
                self._breathe.start()
        else:
            factor = 1 - math.exp(-dt / 0.152)
            nv = int(bar.value() + d * factor)
            if nv != bar.value():
                bar.setValue(nv)
    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._layout()
        self._build()
    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        self._layout()
        self._build()
    def _P(self) -> float:
        return P0 * hud_scale(max(self.width(), 1), max(self.height(), 1))
    def _layout(self) -> None:
        w, h = max(self.width(), 1), max(self.height(), 1)
        P = self._P()
        self.top.setGeometry(int(70 * P), 0, w - int(140 * P), int(70 * P))
        f = self.brand.font()
        f.setPixelSize(max(int(18 * min(P / P0, 1.3)), 10))
        self.brand.setFont(f)
        xf = self.btn_x.font()
        xf.setPixelSize(max(int(26 * min(P / P0, 1.3)), 12))
        self.btn_x.setFont(xf)
        self.scroll.setGeometry(0, int(70 * P), w, h - int(70 * P) - int(104 * P))
        self.scroll.setCursor(Qt.OpenHandCursor)
        orb = int(128 * P)
        self.next.set_scale(P / P0)
        self.next.setGeometry(w - int(28 * P) - orb, h - int(24 * P) - orb, orb, orb)
        self.scroll.horizontalScrollBar().setSingleStep(int(30 * P))
    def render(self, cards: list[dict]) -> None:
        self._cards = list(cards)
        self._build()
    def _build(self) -> None:
        for c in self.track.findChildren(CatCard):
            c.setParent(None)
            c.deleteLater()
        P = self._P()
        card_w = int(CARD_P * P)
        step = int((CARD_P + GAP_P) * P)
        vw, vh = self.scroll.viewport().width(), self.scroll.viewport().height()
        self.track.P = P
        self.track.step = step
        self.track.items = []
        cards = self._cards
        if not cards:
            self._breathe.stop()
            self.track.setFixedSize(vw, vh)
            return
        self.track.setFixedHeight(vh)
        card_h = int(CARD_P * RATIO * P)
        pad_x = int(PAD_X_P * P)
        pad_top = int(PAD_TOP_P * P)
        inner_y = max(0, vh - (card_h + int(PAD_BOTTOM_P * P) + pad_top))
        for i, c in enumerate(cards):
            at = float(c.get("at") or 0) / 1000
            show_month = i == 0 or ym(at) != ym(float(cards[i - 1].get("at") or 0) / 1000)
            is_new = bool(c.get("is_new"))
            card = CatCard(c, is_new, show_month, P, i == len(cards) - 1, self.track)
            card.move(i * step, inner_y)
            card.show()
            self.track.items.append(
                {"x": i * step + pad_x, "y": inner_y + pad_top, "w": card_w,
                 "h": card_h, "is_new": is_new}
            )
        tail = max(0, vw // 2 - card_w // 2)
        total = (len(cards) - 1) * step + card_w + tail
        self.track.setFixedWidth(max(total, vw))
        bar = self.scroll.horizontalScrollBar()
        bar.setValue(bar.maximum())
        self._target = bar.value()
        if any(it["is_new"] for it in self.track.items):
            self._breathe.start()
        else:
            self._breathe.stop()
        self.track.update()

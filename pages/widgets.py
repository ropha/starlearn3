from __future__ import annotations
import html
import math
import re
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QConicalGradient, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QTextDocument
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QVBoxLayout, QWidget
import core
import theme
ORB = (
    ("#FFE680", "#FFB800", "#D98E00", QColor(255, 184, 0, 115)),
    ("#A8D2FF", "#1F7BFF", "#0B4FCC", QColor(31, 123, 255, 107)),
    ("#A6F0C0", "#12C25A", "#08853A", QColor(18, 194, 90, 107)),
    ("#FFB8AE", "#FF4733", "#CC2414", QColor(255, 71, 51, 107)),
)
RAINBOW = ("#FF5E7A", "#FFA62B", "#FFE03D", "#3DDC84", "#2FA8FF", "#8A5CFF", "#F25CD0", "#FF5E7A")
OPT_W = 234
def _shadow(p: QPainter, s: float, y_off: float = 3) -> None:
    for inset, alpha in ((6, 16), (10, 22), (14, 28)):
        i = inset * s / 104.0
        p.setBrush(QColor(110, 80, 30, alpha))
        p.drawEllipse(QRectF(i, i + y_off * s / 104.0, s - i * 2, s - i * 2))
class Orb(QWidget):
    RING = 6.0
    BASE = 72.0
    def __init__(self, index: int, size: int = 72, parent=None, glyph: str | None = None):
        super().__init__(parent)
        self.c1, self.c2, self.c3, self.rim = ORB[index % 4]
        self.glyph = glyph
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(size, size)
    def set_scale(self, k: float) -> None:
        self.setFixedSize(int(self.BASE * k), int(self.BASE * k))
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        u = s / self.BASE
        o = self.RING * u
        d = s - o * 2
        cx = s / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(0, 0, s, s))
        body = QRectF(o, o, d, d)
        p.setBrush(self.rim)
        p.drawEllipse(body.adjusted(-2 * u, -2 * u, 2 * u, 2 * u))
        g = QRadialGradient(QPointF(cx, body.top() + d * 0.30), d * 0.86)
        g.setColorAt(0.0, QColor(self.c1))
        g.setColorAt(0.50, QColor(self.c2))
        g.setColorAt(1.0, QColor(self.c3))
        p.setBrush(g)
        p.drawEllipse(body)
        p.save()
        clip = QPainterPath()
        clip.addEllipse(body)
        p.setClipPath(clip)
        gb = QLinearGradient(body.topLeft(), body.bottomLeft())
        gb.setColorAt(0.00, QColor(255, 255, 255, 0))
        gb.setColorAt(0.62, QColor(255, 255, 255, 0))
        gb.setColorAt(0.88, QColor(252, 242, 226, 82))
        gb.setColorAt(1.00, QColor(252, 242, 226, 118))
        p.setBrush(gb)
        p.drawEllipse(body)
        gr = QRadialGradient(QPointF(cx, body.center().y()), d * 0.5)
        gr.setColorAt(0.00, QColor(0, 0, 0, 0))
        gr.setColorAt(0.86, QColor(0, 0, 0, 0))
        gr.setColorAt(1.00, QColor(70, 58, 38, 44))
        p.setBrush(gr)
        p.drawEllipse(body)
        soft = QRectF(cx - d * 0.33, body.top() + d * 0.05, d * 0.66, d * 0.44)
        gsf = QRadialGradient(soft.center(), d * 0.36)
        gsf.setColorAt(0.0, QColor(255, 255, 255, 85))
        gsf.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(gsf)
        p.drawEllipse(soft)
        hl = QRectF(cx - d * 0.22, body.top() + d * 0.10, d * 0.44, d * 0.24)
        g3 = QLinearGradient(hl.topLeft(), hl.bottomLeft())
        g3.setColorAt(0.00, QColor(255, 255, 255, 200))
        g3.setColorAt(0.50, QColor(255, 255, 255, 104))
        g3.setColorAt(1.00, QColor(255, 255, 255, 0))
        p.setBrush(g3)
        p.drawEllipse(hl)
        p.restore()
        if self.glyph:
            p.setPen(QPen(QColor("#FFFFFF"), max(s * 0.078, 2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            c = QPointF(s / 2, s / 2)
            u = s / 24.0
            if self.glyph == "yes":
                p.drawLine(QPointF(c.x() - 6.6 * u, c.y() + 0.6 * u), QPointF(c.x() - 2.0 * u, c.y() + 4.6 * u))
                p.drawLine(QPointF(c.x() - 2.0 * u, c.y() + 4.6 * u), QPointF(c.x() + 6.6 * u, c.y() - 4.6 * u))
            else:
                p.drawLine(QPointF(c.x() - 5 * u, c.y() - 5 * u), QPointF(c.x() + 5 * u, c.y() + 5 * u))
                p.drawLine(QPointF(c.x() + 5 * u, c.y() - 5 * u), QPointF(c.x() - 5 * u, c.y() + 5 * u))
class NextOrb(QWidget):
    clicked = Signal()
    def __init__(self, size: int = 160, parent=None):
        super().__init__(parent)
        self._base = size
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(size, size)
        self._hue = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)
    def set_scale(self, k: float) -> None:
        self.setFixedSize(int(self._base * k), int(self._base * k))
    def _tick(self) -> None:
        self._hue = (self._hue + 4) % 360
        self.update()
    def mousePressEvent(self, _event) -> None:
        self.clicked.emit()
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        c = QPointF(s / 2, s / 2)
        p.setPen(Qt.NoPen)
        _shadow(p, s)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(8, 8, s - 16, s - 16))
        inner = QRectF(14, 14, s - 28, s - 28)
        cg = QConicalGradient(c, 200)
        for i, col in enumerate(RAINBOW):
            h, sat, v, a = QColor(col).getHsv()
            cg.setColorAt(i / (len(RAINBOW) - 1), QColor.fromHsv((h + self._hue) % 360, sat, v, a))
        p.setBrush(cg)
        p.drawEllipse(inner)
        glass = QRadialGradient(QPointF(c.x(), inner.top() + inner.height() * 0.30), inner.width() * 0.62)
        glass.setColorAt(0.0, QColor(255, 255, 255, 128))
        glass.setColorAt(0.55, QColor(255, 255, 255, 26))
        glass.setColorAt(1.0, QColor(60, 40, 120, 51))
        p.setBrush(glass)
        p.drawEllipse(inner)
        hl = QRectF(inner.x() + inner.width() * 0.21, inner.y() + inner.height() * 0.09, inner.width() * 0.52, inner.height() * 0.32)
        g3 = QLinearGradient(hl.topLeft(), hl.bottomLeft())
        g3.setColorAt(0.0, QColor(255, 255, 255, 235))
        g3.setColorAt(1.0, QColor(255, 255, 255, 15))
        p.setBrush(g3)
        p.drawEllipse(hl)
        u = inner.width() / 24
        pen = QPen(QColor("#FFFFFF"), max(inner.width() * 0.075, 2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(c.x() - 7 * u, c.y()), QPointF(c.x() + 6.5 * u, c.y()))
        p.drawPolyline([QPointF(c.x() + 1.5 * u, c.y() - 5.5 * u), QPointF(c.x() + 6.5 * u, c.y()), QPointF(c.x() + 1.5 * u, c.y() + 5.5 * u)])
class BrandMark(QWidget):
    def __init__(self, size: int = 36, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(size, size)
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.INK))
        p.drawEllipse(QRectF(0, 0, s, s))
        p.setBrush(QColor(theme.BG))
        p.drawEllipse(QRectF(s * 0.28, -s * 0.15, s, s))
        cx, cy, r = s * 0.71, s * 0.29, s * 0.16
        path = QPainterPath()
        for i in range(8):
            ang = math.pi / 2 * (i / 2) - math.pi / 2
            rr = r if i % 2 == 0 else r * 0.42
            x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        path.closeSubpath()
        p.setBrush(QColor(theme.STAR))
        p.drawPath(path)
class StemView(QWidget):
    seg_clicked = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stem")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._item: dict | None = None
        self._seg: int | None = None
        self._k = 1.0
        self._doc_h = 0
        self._doc = QTextDocument(self)
        self._doc.setDocumentMargin(0)
    def set_scale(self, k: float) -> None:
        self._k = k
        if self._item:
            self.render(self._item, self._seg)
    def render(self, item: dict, seg: int | None = None) -> None:
        self._item = item
        seg = 0 if seg is None else seg
        self._seg = seg
        k = self._k
        size = int(30 * k) if item.get("题型") == "picture" else int(52 * k)
        parts = core.stem_segments(item)
        bright0 = seg == 0
        bright1 = seg == 1
        if not parts:
            html_text = self._para(str(item.get("题干") or ""), bright=True, size=size, k=k)
        elif len(parts) >= 2:
            html_text = (
                self._para(parts[0], bright=bright0, size=size, k=k, idx=0)
                + self._para(parts[1], bright=bright1, size=size, k=k, idx=1)
            )
        else:
            html_text = self._para(parts[0], bright=bright0, size=size, k=k, idx=0)
        self._doc.setHtml(html_text)
        self.reflow()
        self.update()
    def reflow(self, width: int | None = None) -> None:
        k = self._k
        w = int(width) if width is not None else self.width()
        self._doc.setTextWidth(max(w - int(8 * k), 1))
        self._doc_h = int(math.ceil(self._doc.size().height()))
        self.setFixedHeight(self._doc_h + int(36 * k))
    def doc_height(self) -> int:
        return self._doc_h
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._doc.drawContents(p)
    def mouseReleaseEvent(self, ev) -> None:
        pos = ev.position()
        layout = self._doc.documentLayout()
        for i in range(self._doc.blockCount()):
            block = self._doc.findBlockByNumber(i)
            if layout.blockBoundingRect(block).contains(pos):
                self.seg_clicked.emit(min(i, 1))
                return
        super().mouseReleaseEvent(ev)
    def set_seg(self, seg: int | None) -> None:
        if self._item:
            self.render(self._item, seg)
    @staticmethod
    def _para(text: str, *, bright: bool, size: int, k: float, idx: int | None = None) -> str:
        color = theme.INK if bright else "#A49A8C"
        size = size if bright else int(size * 0.94)
        if bright:
            rep = (
                '<span style="font-family:\'Noto Sans SC\';font-weight:700;color:'
                + theme.INK
                + ';text-decoration:underline;text-decoration-color:'
                + theme.STAR
                + '">\\1</span>'
            )
        else:
            rep = r"\1"
        body = re.sub(r"(\d+)", rep, html.escape(text)).replace("\n", "<br>")
        if idx is not None:
            body = f'<a href="seg:{idx}" style="text-decoration:none;color:{color}">{body}</a>'
        return (
            f'<p style="color:{color};font-family:\'Noto Sans SC\';font-size:{size}px;font-weight:350;'
            f'line-height:{int(size * 1.52)}px;margin:0 0 {int(18 * k)}px 0">{body}</p>'
        )
class OptNum(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._text = ""
        self._px = 57
        self._state = ""
    def set_text(self, text: str) -> None:
        self._text = text
        self.update()
    def set_px(self, px: int) -> None:
        self._px = max(px, 8)
        self.update()
    def set_state(self, state: str) -> None:
        self._state = state
        self.update()
    def paintEvent(self, _event) -> None:
        if not self._text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        f = QFont(theme.FONT)
        f.setBold(True)
        px = self._px
        max_w = max(self.width() - 6, 8)
        fm = QFontMetrics(f)
        while px > 8:
            f.setPixelSize(px)
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(self._text) <= max_w:
                break
            px -= 1
        p.setFont(f)
        p.setPen(QColor(theme.NO if self._state == "no" else theme.INK))
        adv = fm.horizontalAdvance(self._text)
        baseline = self.height() / 2 + (fm.ascent() - fm.descent()) / 2
        p.drawText(QPointF((self.width() - adv) / 2, baseline), self._text)
class OptionButton(QWidget):
    clicked = Signal(int)
    BASE_W = OPT_W
    BASE_H = 149
    def __init__(self, index: int, parent=None, glyph: str | None = None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("opt")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.BASE_W, self.BASE_H)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 2)
        lay.setSpacing(3)
        self._lay = lay
        self._k = 1.0
        self._state = ""
        self.num = OptNum()
        lay.addWidget(self.num)
        self.orb = Orb(index, glyph=glyph)
        glow = QGraphicsDropShadowEffect(self.orb)
        glow.setBlurRadius(18)
        glow.setOffset(0, 6)
        glow.setColor(QColor(110, 80, 30, 70))
        self.orb.setGraphicsEffect(glow)
        lay.addWidget(self.orb, 0, Qt.AlignHCenter)
    def set_scale(self, k: float) -> None:
        sk = min(k, 1.3)
        self._k = k
        self.setFixedSize(int(self.BASE_W * k), int(self.BASE_H * k))
        self._lay.setContentsMargins(0, max(int(4 * k), 1), 0, max(int(2 * k), 0))
        self._lay.setSpacing(max(int(3 * k), 1))
        self.num.setFixedHeight(int(68 * sk))
        self._sync_num()
        self.orb.set_scale(k)
    def _sync_num(self) -> None:
        sk = min(self._k, 1.3)
        self.num.set_px(int((68 if self._state == "ok" else 57) * sk))
    def set_text(self, text: str) -> None:
        self.num.set_text(text)
    def set_state(self, state: str) -> None:
        self._state = state
        self.num.set_state(state)
        self._sync_num()
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
        if state == "ok":
            halo = QGraphicsDropShadowEffect(self)
            halo.setBlurRadius(32)
            halo.setOffset(0, 0)
            halo.setColor(QColor(47, 184, 98, 155))
            self.setGraphicsEffect(halo)
        else:
            self.setGraphicsEffect(None)
    def mousePressEvent(self, _event) -> None:
        if self.isEnabled():
            self.clicked.emit(self.index)

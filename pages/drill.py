from __future__ import annotations
import html
import re
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget
import theme
from pages.widgets import Orb
OK_MS = 500
LEAVE_MS = 240
ENTER_MS = 320
FLASH_MS = 1000
FLASH_SHAKE_MS = 280
class JudgeCard(QWidget):
    clicked = Signal(bool)
    def __init__(self, yes: bool, parent=None):
        super().__init__(parent)
        self.yes = yes
        self._state = ""
        self._k = 1.0
        self._press = False
        self._flashing = False
        self._anim = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._clear_flash)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self.frame = QWidget(self)
        self.frame.setObjectName("jframe")
        self.frame.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self.frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        self.orb = Orb(2 if yes else 3, glyph="yes" if yes else "no")
        lay.addWidget(self.orb, 0, Qt.AlignHCenter)
        self._apply_style()
    @property
    def state(self) -> str:
        return self._state
    def set_scale(self, k: float) -> None:
        self._k = k
        cw = max(int(198 * k), 1)
        self.setFixedSize(cw, cw)
        self.frame.setGeometry(0, 0, cw, cw)
        self.orb.setFixedSize(max(int(126 * k), 1), max(int(126 * k), 1))
        self._apply_style()
    def _apply_style(self) -> None:
        k = self._k
        if self._state == "ok":
            bg, bc = "#FFFDF8", "rgba(47,184,98,.72)"
            shadow = (
                f"0 0 0 {max(int(8 * k), 1)}px rgba(47,184,98,.12),"
                f"0 {max(int(18 * k), 1)}px {max(int(36 * k), 1)}px rgba(110,80,30,.16)"
            )
        else:
            bg, bc = "rgba(255,252,245,.72)", "rgba(58,46,34,.10)"
            shadow = f"0 {max(int(8 * k), 1)}px {max(int(18 * k), 1)}px rgba(110,80,30,.08)"
        self.frame.setStyleSheet(
            f"QWidget#jframe{{background:{bg};border:{max(int(3 * k), 2)}px solid {bc};"
            f"border-radius:{max(int(40 * k), 1)}px;box-shadow:{shadow};}}"
        )
        drop = QGraphicsDropShadowEffect(self.frame)
        drop.setBlurRadius(max(int(16 * k), 1))
        drop.setOffset(0, max(int(8 * k), 1))
        drop.setColor(QColor(110, 80, 30, 26 if self._state == "ok" else 18))
        self.frame.setGraphicsEffect(drop)
        if self._state == "ok":
            glow = QGraphicsDropShadowEffect(self.orb)
            glow.setBlurRadius(max(int(34 * k), 1))
            glow.setOffset(0, 0)
            glow.setColor(QColor(18, 194, 90, 150))
            self.orb.setGraphicsEffect(glow)
        else:
            self.orb.setGraphicsEffect(None)
    def set_state(self, state: str) -> None:
        self._clear_flash()
        self._state = state
        if state in ("dim", "no"):
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.30 if state == "dim" else 0.45)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)
        self._apply_style()
        self.update()
    def flash(self) -> None:
        self._clear_flash()
        self._state = "no"
        self._flashing = True
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.45)
        self.setGraphicsEffect(eff)
        self._apply_style()
        base = QPoint(self.x(), self.y())
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(FLASH_SHAKE_MS)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._anim.setKeyValueAt(0.0, base)
        self._anim.setKeyValueAt(0.35, QPoint(base.x() + int(-3 * self._k), base.y()))
        self._anim.setKeyValueAt(0.70, QPoint(base.x() + int(2 * self._k), base.y()))
        self._anim.setKeyValueAt(1.0, base)
        self._anim.start()
        self._timer.start(FLASH_MS)
        self.update()
    def _clear_flash(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        self._timer.stop()
        if self._flashing:
            self._flashing = False
            self._state = ""
            self.setGraphicsEffect(None)
            self._apply_style()
            self.update()
    def mousePressEvent(self, _ev) -> None:
        if not self._state:
            self._press = True
            self.update()
    def mouseReleaseEvent(self, ev) -> None:
        was = self._press
        self._press = False
        self.update()
        if was and not self._state and self.rect().contains(ev.pos()):
            self.clicked.emit(self.yes)
class DrillView(QWidget):
    judge = Signal(bool)
    row_shown = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.k = 1.0
        self.item: dict | None = None
        self.row = 0
        self.eq = QLabel(self)
        self.eq.setAlignment(Qt.AlignCenter)
        self.eq.setTextFormat(Qt.RichText)
        self.yes = JudgeCard(True, self)
        self.no = JudgeCard(False, self)
        self.yes.clicked.connect(lambda: self.judge.emit(True))
        self.no.clicked.connect(lambda: self.judge.emit(False))
        self._eq_eff = QGraphicsOpacityEffect(self.eq)
        self.eq.setGraphicsEffect(self._eq_eff)
        self._anim: QPropertyAnimation | None = None
        self._op_anim: QPropertyAnimation | None = None
        self._swap_timer = QTimer(self)
        self._swap_timer.setSingleShot(True)
        self._swap_timer.timeout.connect(self._do_swap)
        self._pending_text = ""
        self._pending_row = 0
        self._swap_base: QPoint | None = None
        self.stamp = QLabel("✓", self)
        self.stamp.setAlignment(Qt.AlignCenter)
        stamp_sh = QGraphicsDropShadowEffect(self.stamp)
        stamp_sh.setBlurRadius(11)
        stamp_sh.setOffset(0, 3)
        stamp_sh.setColor(QColor(120, 90, 40, 100))
        self.stamp.setGraphicsEffect(stamp_sh)
        self.stamp.hide()
    def set_scale(self, k: float) -> None:
        self.k = k
        self.yes.set_scale(k)
        self.no.set_scale(k)
        self.eq.setStyleSheet(f"font-family:'{theme.FONT}';font-size:{int(190 * min(k, 1.3))}px;")
        sz = max(int(54 * k), 1)
        self.stamp.setFixedSize(sz, sz)
        self.stamp.setStyleSheet(
            f"background:#2FB862;color:#fff;border:{max(int(5 * k), 2)}px solid #FFFFFF;"
            f"border-radius:{sz // 2}px;font-size:{int(30 * min(k, 1.3))}px;font-weight:bold;"
        )
        self._layout()
        if self.item is not None:
            rows = (self.item.get("选项") or [])[:5]
            if rows:
                self.eq.setText(self._eq_html(rows[min(self.row, len(rows) - 1)]["算式"]))
    def _layout(self) -> None:
        w, h = max(self.width(), 1), max(self.height(), 1)
        k = self.k
        self.eq.setGeometry(0, int(h * 0.24) - int(10 * k), w, int(210 * k))
        cw = max(int(198 * k), 1)
        gap = max(int(58 * k), 1)
        x0 = (w - (cw * 2 + gap)) // 2
        y = max(h - max(int(8 * k), 0) - cw, 0)
        self.yes.setGeometry(x0, y, cw, cw)
        self.no.setGeometry(x0 + cw + gap, y, cw, cw)
    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._layout()
    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        self._layout()
    def render(self, item: dict, row: int) -> None:
        self._swap_timer.stop()
        changing = self.item is not None and row != self.row
        self.item = item
        self.row = row
        self.stamp.hide()
        for c in (self.yes, self.no):
            c._clear_flash()
            c.set_state("")
        rows = (item.get("选项") or [])[:5]
        text = self._eq_html(rows[min(row, len(rows) - 1)]["算式"])
        if self._anim is not None:
            self._anim.stop()
        if self._op_anim is not None:
            self._op_anim.stop()
            self._op_anim.deleteLater()
            self._op_anim = None
        if not changing:
            self.eq.setText(text)
            self._eq_eff.setOpacity(1.0)
            self.row_shown.emit(row)
            return
        self._pending_text = text
        self._pending_row = row
        base = QPoint(self.eq.x(), self.eq.y())
        self._swap_base = base
        self._anim = QPropertyAnimation(self.eq, b"pos", self)
        self._anim.setDuration(LEAVE_MS)
        self._anim.setEasingCurve(QEasingCurve.InQuad)
        self._anim.setKeyValueAt(0.0, base)
        self._anim.setKeyValueAt(1.0, QPoint(base.x() - int(60 * self.k), base.y()))
        self._anim.start()
        self._op_anim = QPropertyAnimation(self._eq_eff, b"opacity", self)
        self._op_anim.setDuration(LEAVE_MS)
        self._op_anim.setStartValue(1.0)
        self._op_anim.setEndValue(0.0)
        self._op_anim.start()
        self._swap_timer.start(LEAVE_MS)
    def _do_swap(self) -> None:
        if self._op_anim is not None:
            self._op_anim.stop()
            self._op_anim.deleteLater()
            self._op_anim = None
        self.eq.setText(self._pending_text)
        base = self._swap_base or QPoint(self.eq.x(), self.eq.y())
        self._anim = QPropertyAnimation(self.eq, b"pos", self)
        self._anim.setDuration(ENTER_MS)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._anim.setKeyValueAt(0.0, QPoint(base.x() + int(60 * self.k), base.y()))
        self._anim.setKeyValueAt(1.0, base)
        self._anim.start()
        self._op_anim = QPropertyAnimation(self._eq_eff, b"opacity", self)
        self._op_anim.setDuration(ENTER_MS)
        self._op_anim.setStartValue(0.0)
        self._op_anim.setEndValue(1.0)
        self._op_anim.start()
        self.row_shown.emit(self._pending_row)
    def mark_ok(self, yes: bool) -> None:
        target = self.yes if yes else self.no
        target.set_state("ok")
        k = self.k
        sz = self.stamp.width() or max(int(54 * k), 1)
        self.stamp.move(
            int(target.x() + target.width() + 16 * k - sz),
            int(target.y() - 16 * k),
        )
        self.stamp.show()
        (self.no if yes else self.yes).set_state("dim")
    def flash_wrong(self, yes: bool) -> None:
        (self.yes if yes else self.no).flash()
    def finish(self) -> None:
        for c in (self.yes, self.no):
            if c.state != "ok":
                c.set_state("dim")
    def _eq_html(self, text: str) -> str:
        ink, muted = theme.INK, theme.MUTED
        px = int(190 * min(self.k, 1.3))
        out = [f'<div style="line-height:{px}px;">']
        for part in re.split(r"([+−=])", str(text)):
            if not part:
                continue
            if part in ("+", "−", "="):
                out.append(f'<span style="color:{muted};font-weight:400">{html.escape(part)}</span>')
            else:
                out.append(f'<span style="color:{ink}">{html.escape(part)}</span>')
        out.append("</div>")
        return "".join(out)

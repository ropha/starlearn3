from __future__ import annotations
import math
import time
from PySide6.QtCore import QByteArray, QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import theme
from confetti import Confetti
from pages.drill import DrillView
from pages.hud import BOTTOM, RIGHT, ParentHud, hud_scale
from pages.widgets import BrandMark, NextOrb, OptionButton, OPT_W, StemView
BASE_W, BASE_H = 1440, 900
OPT_H = 149
OPT_X = (99, 351, 603, 855)
NEXT_W = 148
FLASH_MS = 1000
FLASH_SHAKE_MS = 280
FLASH_OPACITY = 0.45
FLASH_SHAKE = (-3, 2)
class _WaitDots(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.k = 1.0
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self.hide()
    def set_scale(self, k: float) -> None:
        self.k = k
        self.update()
    def showEvent(self, ev) -> None:
        self._t0 = time.monotonic()
        self._timer.start()
        super().showEvent(ev)
    def hideEvent(self, ev) -> None:
        self._timer.stop()
        super().hideEvent(ev)
    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        d = 22 * self.k
        gap = 22 * self.k
        x0 = (self.width() - (d * 3 + gap * 2)) / 2
        y = (self.height() - d) / 2
        t = time.monotonic() - self._t0
        for i in range(3):
            u = ((t - i * 0.2) % 1.4) / 1.4
            a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2 * math.pi * u - math.pi / 2))
            p.setBrush(QColor(217, 205, 184, int(255 * a)))
            p.drawEllipse(QRectF(x0 + i * (d + gap), y, d, d))
class QuizPage(QWidget):
    pick = Signal(int)
    stem_click = Signal(int)
    drill_judge = Signal(bool)
    next_item = Signal()
    next_ready = Signal()
    skip = Signal(str)
    undo_wrong = Signal()
    quit = Signal()
    note_entered = Signal(str)
    def __init__(self):
        super().__init__()
        self._item: dict | None = None
        self.k = 1.0
        self._svg_size = (0, 0)
        self._flash_index: int | None = None
        self._flash_base: QPoint | None = None
        self._flash_anim: QPropertyAnimation | None = None
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self._end_arm = False
        self._end_timer = QTimer(self)
        self._end_timer.setSingleShot(True)
        self._end_timer.timeout.connect(self._disarm_end)
        self._next_delay = False
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._reveal_next)
        self._card_lock = False
        self._enter_anims: list = []
        self._enter_gen = 0
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(BrandMark(27))
        self.brand = QLabel("  Ai数学老师")
        self.brand.setObjectName("brand")
        top.addWidget(self.brand)
        top.addStretch(1)
        self.btn_undo = QPushButton("点错了？")
        self.btn_undo.setObjectName("ghost")
        self.btn_undo.setCursor(Qt.PointingHandCursor)
        self.btn_undo.hide()
        self.btn_undo.clicked.connect(self.undo_wrong.emit)
        top.addWidget(self.btn_undo)
        self.btn_skip = QPushButton("跳过")
        self.btn_skip.setObjectName("ghost")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.clicked.connect(self._open_skip)
        top.addWidget(self.btn_skip)
        self.btn_quit = QPushButton("×")
        self.btn_quit.setObjectName("ghost")
        self.btn_quit.setCursor(Qt.PointingHandCursor)
        self.btn_quit.clicked.connect(self._on_quit_click)
        top.addWidget(self.btn_quit)
        self.top = QWidget(self)
        self.top.setLayout(top)
        self.stem = StemView(self)
        self.stem.seg_clicked.connect(self.stem_click.emit)
        self.svg = QSvgWidget(self)
        self.svg.hide()
        self.drill = DrillView(self)
        self.drill.hide()
        self.drill.judge.connect(self.drill_judge.emit)
        self.options: list[OptionButton] = []
        for i in range(4):
            b = OptionButton(i, self)
            b.clicked.connect(lambda idx: self.pick.emit(idx))
            self.options.append(b)
        self.next_orb = NextOrb(NEXT_W, self)
        self.next_orb.clicked.connect(self.next_item.emit)
        self.next_orb.hide()
        self.next_lab = QLabel("下一题", self)
        self.next_lab.setObjectName("lab")
        self.next_lab.setAlignment(Qt.AlignCenter)
        self.next_lab.hide()
        self.hud = ParentHud(self)
        self.hud.hide()
        self.skip_modal = SkipModal(self)
        self.skip_modal.hide()
        self.skip_modal.chosen.connect(self._skip)
        self.skip_modal.closed.connect(self._close_skip)
        self.stamp = QLabel("✓", self)
        self.stamp.setAlignment(Qt.AlignCenter)
        stamp_sh = QGraphicsDropShadowEffect(self.stamp)
        stamp_sh.setBlurRadius(11)
        stamp_sh.setOffset(0, 3)
        stamp_sh.setColor(QColor(120, 90, 40, 100))
        self.stamp.setGraphicsEffect(stamp_sh)
        self.stamp.hide()
        self.confetti = Confetti(self)
        self.wait = _WaitDots(self)
        self.slots: list[QWidget] = []
        for _ in range(4):
            s = QWidget(self)
            s.setObjectName("slot")
            s.hide()
            self.slots.append(s)
        self.note = QLineEdit(self)
        self.note.setObjectName("note")
        self.note.setPlaceholderText("家长备注，回车保存，Esc 取消")
        self.note.returnPressed.connect(self._submit_note)
        self.note.hide()
        self.note_ok = QLabel("已记录 ✓", self)
        self.note_ok.setObjectName("lab")
        self.note_ok.setAlignment(Qt.AlignCenter)
        self.note_ok.hide()
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout()
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._layout()
    def show_waiting(self) -> None:
        for w in (self.stem, self.svg, self.drill, self.next_orb, self.next_lab,
                  self.stamp, self.hud, self.note, self.note_ok, self.btn_skip):
            w.hide()
        for b in self.options:
            b.hide()
        for s in self.slots:
            s.show()
            s.raise_()
        self.wait.show()
        self.wait.raise_()
    def hide_waiting(self) -> None:
        self.wait.hide()
        for s in self.slots:
            s.hide()
        self.btn_skip.show()
    def show_note(self) -> None:
        if not self._item:
            return
        self.note.clear()
        self.note.show()
        self.note.raise_()
        self.note.setFocus()
    def _submit_note(self) -> None:
        text = self.note.text().strip()
        self.note.hide()
        if not text:
            return
        self.note_entered.emit(text)
        self.note_ok.show()
        self.note_ok.raise_()
        QTimer.singleShot(1200, self.note_ok.hide)
    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Escape and self.note.isVisible():
            self.note.hide()
            return
        super().keyPressEvent(ev)
    def _layout(self) -> None:
        w, h = max(self.width(), 1), max(self.height(), 1)
        k = min(w / BASE_W, h / BASE_H)
        sk = min(k, 1.3)
        self.k = k
        self.top.setGeometry(int(99 * k), 0, int(1242 * k), int(72 * k))
        bf = self.brand.font()
        bf.setPixelSize(max(int(18 * sk), 10))
        bf.setBold(False)
        self.brand.setFont(bf)
        self.btn_skip.setFixedHeight(max(int(48 * k), 20))
        self.btn_quit.setFixedHeight(max(int(48 * k), 20))
        self._apply_quit_style()
        stem_h = self.stem.doc_height() or int(250 * sk)
        stem_w = int(996 * sk)
        opt_y = h - int(33 * k) - int(OPT_H * k)
        top_y = int(72 * k)
        if self._svg_size[0] > 0:
            stem_y = top_y + int(24 * k)
        else:
            stem_y = int(234 * k)
        self.stem.setGeometry(int(99 * k), stem_y, stem_w, stem_h)
        self.stem.set_scale(sk)
        self.stem.reflow(stem_w)
        stem_h = self.stem.doc_height()
        svg_top = stem_y + stem_h + int(12 * k)
        svg_h = max(opt_y - svg_top - int(12 * k), 0)
        if self._svg_size[0] > 0 and svg_h > 0:
            sw, sh = self._svg_size
            fit = min(stem_w / sw, svg_h / sh)
            fw, fh = max(int(sw * fit), 1), max(int(sh * fit), 1)
            self.svg.setGeometry(int(99 * k) + (stem_w - fw) // 2, svg_top, fw, fh)
        for i, b in enumerate(self.options):
            b.set_scale(k)
            b.setGeometry(int(OPT_X[i] * k), opt_y, int(OPT_W * k), int(OPT_H * k))
        for i, s in enumerate(self.slots):
            s.setGeometry(int(OPT_X[i] * k), opt_y, int(OPT_W * k), int(OPT_H * k))
        self.wait.setGeometry(0, int(h * 0.34), w, int(44 * k))
        self.wait.set_scale(k)
        self.note.setGeometry(int((w - 720 * k) / 2), opt_y - int(58 * k), int(720 * k), int(46 * k))
        self.note.setStyleSheet(f"font-size:{max(int(20 * sk), 10)}px;")
        self.note_ok.setGeometry(int((w - 220 * k) / 2), opt_y - int(58 * k), int(220 * k), int(46 * k))
        self.next_orb.set_scale(k)
        orb_y = h - int(33 * k) - int(186 * k)
        self.next_orb.setGeometry(int(1150 * k), orb_y, int(NEXT_W * k), int(NEXT_W * k))
        self.next_lab.setGeometry(int(1150 * k), orb_y + int(162 * k), int(NEXT_W * k), int(26 * sk))
        self.next_lab.setStyleSheet(f"font-size:{int(24 * sk)}px;font-weight:bold;color:{theme.INK};")
        self.stamp.setFixedSize(int(48 * k), int(48 * k))
        self.stamp.setStyleSheet(
            f"background:#2FB862;color:#fff;border:{max(int(5 * k), 2)}px solid #FFFFFF;"
            f"border-radius:{int(24 * k)}px;font-size:{int(22 * sk)}px;font-weight:bold;"
        )
        hk = hud_scale(w, h)
        hw, hh = int(160 * hk), int(60 * hk)
        self.hud.set_scale(hk)
        self.hud.setGeometry(w - int(RIGHT * hk) - hw, h - int(BOTTOM * hk) - hh, hw, hh)
        self.drill.setGeometry(0, 0, w, h)
        self.drill.set_scale(k)
        if not self.confetti.isVisible():
            self.confetti.setGeometry(self.rect())
    def _apply_quit_style(self) -> None:
        k, sk = self.k, min(self.k, 1.3)
        if self._end_arm:
            self.btn_quit.setFixedWidth(max(int(104 * k), 32))
            self.btn_quit.setStyleSheet(f"QPushButton#ghost{{color:{theme.INK};}}")
            px = int(20 * sk)
        else:
            self.btn_quit.setFixedWidth(max(int(64 * k), 24))
            self.btn_quit.setStyleSheet("")
            px = int(26 * sk)
        f = self.btn_quit.font()
        f.setPixelSize(max(px, 12))
        self.btn_quit.setFont(f)
    def _on_quit_click(self) -> None:
        if self.wait.isVisible() or self._end_arm:
            self._disarm_end()
            self.quit.emit()
            return
        self._end_arm = True
        self.btn_quit.setText("结束?")
        self._apply_quit_style()
        self._end_timer.start(3000)
    def _disarm_end(self) -> None:
        self._end_timer.stop()
        if not self._end_arm:
            return
        self._end_arm = False
        self.btn_quit.setText("×")
        self._apply_quit_style()
    def celebrate(self, index: int) -> None:
        b = self.options[index]
        self.confetti.burst(b.x() + b.width() / 2, b.y() + b.height() * 0.35)
    def celebrate_drill(self, item: dict) -> None:
        rows = (item.get("选项") or [])[:5]
        yes = bool(rows[-1].get("成立")) if rows else True
        b = self.drill.yes if yes else self.drill.no
        self.confetti.burst(b.x() + b.width() / 2, b.y() + b.height() * 0.35)
    def celebrate_drill_row(self, item: dict, row: int) -> None:
        rows = (item.get("选项") or [])[:5]
        if not rows or row < 0 or row >= len(rows):
            return
        b = self.drill.yes if bool(rows[row].get("成立")) else self.drill.no
        self.confetti.burst(b.x() + b.width() / 2, b.y() + b.height() * 0.35)
    def _arm_next(self) -> None:
        self._next_delay = True
        self.next_orb.hide()
        self.next_lab.hide()
        self._next_timer.stop()
        if not self._card_lock:
            self._next_timer.start(300)
    def lock_next_for_card(self) -> None:
        self._card_lock = True
        self._next_timer.stop()
        self.next_orb.hide()
        self.next_lab.hide()
    def unlock_next(self) -> None:
        if not self._card_lock:
            return
        self._card_lock = False
        self._reveal_next()
    def _reveal_next(self) -> None:
        self._next_delay = False
        self.next_orb.setGraphicsEffect(None)
        self.next_orb.show()
        self.next_lab.show()
        k = self.k
        eff = QGraphicsOpacityEffect(self.next_orb)
        eff.setOpacity(0.0)
        self.next_orb.setGraphicsEffect(eff)
        oa = QPropertyAnimation(eff, b"opacity", self)
        oa.setDuration(340)
        oa.setStartValue(0.0)
        oa.setEndValue(1.0)
        oa.start()
        self.next_ready.emit()
    def _animate_item_enter(self) -> None:
        self._clear_item_enter()
        self._enter_gen += 1
        gen = self._enter_gen
        k = self.k
        widgets: list[tuple[QWidget, int]] = []
        if self.drill.isVisible():
            widgets = [(self.drill.eq, 0)]
        else:
            widgets.append((self.stem, 0))
            if self.svg.isVisible():
                widgets.append((self.svg, 40))
        def run(w: QWidget) -> None:
            base = w.pos()
            pa = QPropertyAnimation(w, b"pos", self)
            pa.setDuration(400)
            pa.setEasingCurve(QEasingCurve.OutCubic)
            pa.setStartValue(QPoint(base.x(), base.y() + int(10 * k)))
            pa.setEndValue(base)
            self._enter_anims.append(pa)
            pa.start()
        for w, delay in widgets:
            if delay:
                QTimer.singleShot(delay, lambda w=w: run(w))
            else:
                run(w)
        QTimer.singleShot(520, lambda g=gen: self._clear_item_enter(g))
    def _clear_item_enter(self, gen: int | None = None) -> None:
        if gen is not None and gen != self._enter_gen:
            return
        for a in self._enter_anims:
            try:
                a.stop()
            except RuntimeError:
                pass
        self._enter_anims = []
    def render(self, item: dict, index: int, total: int) -> None:
        self._item = item
        self.hide_waiting()
        self.note.hide()
        self.note_ok.hide()
        self.hud.set_item(item.get("难度分数"), item.get("预测答题时长"), int(time.time() * 1000))
        self.hud.show()
        self._disarm_end()
        self.stamp.hide()
        self.next_orb.hide()
        self.next_lab.hide()
        self.btn_undo.hide()
        self._clear_flash()
        self._clear_item_enter()
        self._next_timer.stop()
        self._next_delay = False
        self._card_lock = False
        self.skip_modal.hide()
        self.confetti.clear()
        if item.get("题型") == "drill":
            self.stem.hide()
            self.svg.hide()
            self._svg_size = (0, 0)
            for b in self.options:
                b.hide()
            self.drill.show()
            self.drill.render(item, 0)
            self._layout()
            self._animate_item_enter()
            return
        self.drill.hide()
        self.stem.show()
        self.stem.render(item, 0)
        svg = item.get("图")
        if item.get("题型") == "picture" and svg:
            self.svg.load(QByteArray(str(svg).encode("utf-8")))
            vb = self.svg.renderer().viewBoxF()
            self._svg_size = (int(vb.width()), int(vb.height())) if vb.width() > 0 else (0, 0)
            self.svg.show()
        else:
            self._svg_size = (0, 0)
            self.svg.hide()
        for i, b in enumerate(self.options):
            b.show()
            b.set_text(str(item["选项"][i]))
            b.setEnabled(True)
            b.set_state("")
            b.setGraphicsEffect(None)
        self._layout()
        self._animate_item_enter()
    def render_drill(self, item: dict, row: int) -> None:
        self._item = item
        self.drill.show()
        self.drill.render(item, row)
    def show_feedback(self, ok: bool, answer: int, picked: int) -> None:
        if self._item and self._item.get("题型") == "drill":
            self.drill.finish()
            self._arm_next()
            self.btn_undo.hide()
            return
        self.options[answer].set_state("ok")
        if not ok:
            self.options[picked].set_state("no")
        for i, b in enumerate(self.options):
            if i != answer:
                eff = QGraphicsOpacityEffect(b)
                eff.setOpacity(0.30)
                b.setGraphicsEffect(eff)
        self._arm_next()
        self.btn_undo.hide()
        self._clear_flash()
        target = self.options[answer]
        self.stamp.move(target.x() + target.width() - int(34 * self.k), target.y() - int(27 * self.k))
        self.stamp.show()
    def flash_wrong(self, index: int) -> None:
        self._end_flash()
        b = self.options[index]
        eff = QGraphicsOpacityEffect(b)
        eff.setOpacity(FLASH_OPACITY)
        b.setGraphicsEffect(eff)
        self._flash_index = index
        self._flash_base = b.pos()
        self._flash_anim = QPropertyAnimation(b, b"pos", self)
        self._flash_anim.setDuration(FLASH_SHAKE_MS)
        self._flash_anim.setEasingCurve(QEasingCurve.OutQuad)
        p0 = self._flash_base
        dx1 = int(FLASH_SHAKE[0] * self.k)
        dx2 = int(FLASH_SHAKE[1] * self.k)
        self._flash_anim.setKeyValueAt(0.0, p0)
        self._flash_anim.setKeyValueAt(0.35, QPoint(p0.x() + dx1, p0.y()))
        self._flash_anim.setKeyValueAt(0.70, QPoint(p0.x() + dx2, p0.y()))
        self._flash_anim.setKeyValueAt(1.0, p0)
        self._flash_anim.start()
        self._flash_timer.start(FLASH_MS)
        self.btn_undo.show()
    def _end_flash(self) -> None:
        if self._flash_anim is not None:
            self._flash_anim.stop()
            self._flash_anim = None
        self._flash_timer.stop()
        if self._flash_index is not None:
            b = self.options[self._flash_index]
            b.setGraphicsEffect(None)
            if self._flash_base is not None:
                b.move(self._flash_base)
            self._flash_index = None
            self._flash_base = None
    def _clear_flash(self) -> None:
        self._end_flash()
        self.btn_undo.hide()
    def _open_skip(self) -> None:
        self.skip_modal.setGeometry(self.rect())
        self.skip_modal.relayout()
        self.skip_modal.show()
        self.skip_modal.raise_()
    def _close_skip(self) -> None:
        self.skip_modal.hide()
    def _skip(self, reason: str) -> None:
        self.skip_modal.hide()
        self.skip.emit(reason)
    def set_seg(self, seg: int | None) -> None:
        self.stem.set_seg(seg)
class SkipModal(QWidget):
    chosen = Signal(str)
    closed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.ArrowCursor)
        self._p = 1.0
        self.card = QWidget(self)
        self.card.setObjectName("skipCard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        self.title = QLabel("为什么跳过？", self.card)
        self.title.setObjectName("skipTitle")
        self.x = QPushButton("×", self.card)
        self.x.setObjectName("skipX")
        self.x.setCursor(Qt.PointingHandCursor)
        self.x.clicked.connect(self.closed.emit)
        self.opt1 = QPushButton("我不会", self.card)
        self.opt2 = QPushButton("题目有问题", self.card)
        for b, reason in ((self.opt1, "我不会"), (self.opt2, "题目有问题")):
            b.setObjectName("skipOpt")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, r=reason: self.chosen.emit(r))
    def relayout(self) -> None:
        w, h = self.width(), self.height()
        p = hud_scale(max(w, 1), max(h, 1))
        self._p = p
        px = lambda v: max(int(round(v * p)), 1)
        cw, ch = min(px(640), int(w * 0.86)), px(300)
        cx, cy = (w - cw) // 2, (h - ch) // 2
        self.card.setGeometry(cx, cy, cw, ch)
        self.card.setStyleSheet(
            f"QWidget#skipCard{{background:{theme.PAGE};border-radius:{px(36)}px;}}"
        )
        title_sz, opt_sz = px(40), px(34)
        pad = px(48)
        tf = self.title.font()
        tf.setPixelSize(title_sz)
        tf.setBold(True)
        self.title.setFont(tf)
        self.title.setGeometry(pad, pad, cw - pad * 2, px(52))
        self.title.setStyleSheet(f"color:{theme.INK};font-weight:700;")
        xf = self.x.font()
        xf.setPixelSize(px(40))
        self.x.setFont(xf)
        self.x.setGeometry(cw - px(60), px(14), px(46), px(46))
        self.x.setStyleSheet(f"QPushButton#skipX{{background:transparent;border:none;color:{theme.MUTED};}}")
        oh = px(84)
        gap = px(18)
        oy = pad + px(52) + px(8)
        opt_style = (
            f"QPushButton#skipOpt{{background:transparent;border:{max(px(2),1)}px solid {theme.LINE};"
            f"border-radius:{px(28)}px;color:{theme.INK};text-align:left;padding-left:{px(28)}px;"
            f"font-weight:600;}}"
            f"QPushButton#skipOpt:hover{{border-color:{theme.INK};}}"
        )
        for b, yy in ((self.opt1, oy), (self.opt2, oy + oh + gap)):
            of = b.font()
            of.setPixelSize(opt_sz)
            of.setBold(True)
            b.setFont(of)
            b.setGeometry(pad, yy, cw - pad * 2, oh)
            b.setStyleSheet(opt_style)
    def mousePressEvent(self, event) -> None:
        if not self.card.geometry().contains(event.pos()):
            self.closed.emit()
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(58, 46, 34, int(255 * 0.35)))

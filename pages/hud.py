from __future__ import annotations
import math
import time
from pathlib import Path
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QWidget
import theme
_FAMILY = theme.FONT
_FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
_LOADED = False
def _load_fonts() -> None:
    global _FAMILY, _LOADED
    if _LOADED:
        return
    _LOADED = True
    for name in ("Medium", "SemiBold"):
        f = _FONT_DIR / ("InstrumentSans-" + name + ".ttf")
        if not f.exists():
            continue
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            fam = QFontDatabase.applicationFontFamilies(fid)
            if fam:
                _FAMILY = fam[0]
P0 = 0.748896
RIGHT = 7.48896
BOTTOM = 5.99117
NUMS_H = 25.45
PTXT_H = 9.73565
GAP_OUT = 3.74448
GAP_COL = 2.99559
GAP_NUMS = 4.49338
BAR_W = 1.48
DIFF_PX = 12.7312
PRED_PX = 9.73565
PTXT_PX = 8.98676
FADE_MS = 1000
FADE_HOLD_MS = 350
def hud_scale(w: int, h: int) -> float:
    u = min(3.7795, 0.003 * h, w / 598.0)
    return u * 0.311 / P0
def sign(v) -> str:
    return "-" if v == -1 else "+" if v == 1 else ""
def hud_text(key: int, p: dict) -> str:
    if key in (1, 3):
        return ""
    if key == 2:
        return "trying" if p.get("在努力") else "away" if p.get("分心了") else ""
    if key == 4:
        return "oload" if p.get("题面措辞导致脑超载") else "unclear" if p.get("题面不清晰") else ""
    return "helped" if p.get("家长帮解答") else "refocus" if p.get("家长帮回神") else ""
class ParentHud(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        _load_fonts()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._k = 1.0
        self._diff = ""
        self._pred = ""
        self._text = ""
        self._frac = 1.0
        self._alpha = 0.0
        self._shown = 0.0
        self._text_at = 0.0
        self._pred_s = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)
    def set_scale(self, k: float) -> None:
        self._k = k
        self.update()
    def set_item(self, diff, pred, shown_ms: int) -> None:
        self._diff = str(diff if diff is not None else "")
        self._pred = str(pred if pred is not None else "")
        self._pred_s = int(pred or 0)
        self._shown = float(shown_ms)
        self._text = ""
        self._text_at = 0.0
        self._alpha = 0.0
        self._tick()
    def set_parent(self, key: int, p: dict, diff, pred) -> None:
        self._diff = str(diff if diff is not None else "") + sign(p.get("难度分数修正"))
        self._pred = str(pred if pred is not None else "") + sign(p.get("预测答题时长修正"))
        self._text = hud_text(key, p)
        self._text_at = time.time() * 1000
        self._alpha = 1.0
        self.update()
    def stop(self) -> None:
        self.hide()
    def freeze(self, frac: float) -> None:
        self._pred_s = 0
        self._frac = frac
        self.update()
    def _tick(self) -> None:
        now = time.time() * 1000
        if self._pred_s > 0:
            self._frac = max(0.0, min(1.0, 1 - (now - self._shown) / (self._pred_s * 1000)))
        if self._text:
            dt = now - self._text_at
            if dt <= FADE_HOLD_MS:
                self._alpha = 1.0
            else:
                t = min((dt - FADE_HOLD_MS) / (FADE_MS - FADE_HOLD_MS), 1.0)
                self._alpha = (1 - t) ** 3
                if self._alpha <= 0:
                    self._text = ""
        self.update()
    def _line(self, p: QPainter, text: str, px: float, size: int, weight: int, right: float, top: float, alpha: float, spacing: float = 0) -> None:
        if not text:
            return
        f = QFont(_FAMILY)
        f.setPixelSize(max(size, 1))
        f.setWeight(QFont.Weight(weight))
        f.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)
        if spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        p.setFont(f)
        p.setPen(QColor(58, 46, 34, round(41 * alpha)))
        fm = p.fontMetrics()
        p.drawText(QPointF(right - fm.horizontalAdvance(text), top + px / 2 + fm.capHeight() / 2), text)
    def paintEvent(self, _event) -> None:
        k = self._k
        w, h = self.width(), self.height()
        nums_bottom = h - (PTXT_H + GAP_OUT) * k
        nums_top = nums_bottom - NUMS_H * k
        bw = max(1, math.ceil(BAR_W * k))
        bar_x = w - bw
        col_right = bar_x - GAP_NUMS * k
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.TextAntialiasing)
        dy = 2 * k
        self._line(p, self._diff, DIFF_PX * k, int(DIFF_PX * k), 600, col_right, nums_top - dy, 1.0)
        pred_right = col_right + (k if len(self._pred) > 1 else 0)
        self._line(p, self._pred, PRED_PX * k, int(PRED_PX * k), 500, pred_right, nums_top + (DIFF_PX + GAP_COL) * k - dy, 1.0)
        self._line(p, self._text, PTXT_PX * k, round(PTXT_PX * k), 500, w - k, nums_bottom + GAP_OUT * k - k, self._alpha, 0.03 * PTXT_PX * k)
        bar_bottom = nums_bottom + k
        fill_h = NUMS_H * k * self._frac
        if fill_h > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(58, 46, 34, 41))
            p.drawRect(bar_x, bar_bottom - fill_h, bw, fill_h)
        p.end()
        QPainter(self).drawImage(0, 0, img)

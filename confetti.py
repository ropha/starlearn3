from __future__ import annotations
import math
import os
import random
import time
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget
COLORS = ("#FF5E7A", "#FFA62B", "#FFE03D", "#3DDC84", "#2FA8FF", "#8A5CFF", "#F25CD0")
DURATION = 1.4
COUNT = 96
class Confetti(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()
        self._parts: list[dict] = []
        self._t0 = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
    def burst(self, x: float, y: float) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self._parts = []
        for _ in range(COUNT):
            angle = random.uniform(math.pi * 1.02, math.pi * 1.98)
            speed = random.uniform(6.0, 17.0)
            self._parts.append({
                "p": QPointF(x, y),
                "v": QPointF(math.cos(angle) * speed, math.sin(angle) * speed),
                "rot": random.uniform(0, 360),
                "vr": random.uniform(-18, 18),
                "w": random.uniform(5, 10),
                "h": random.uniform(10, 20),
                "c": QColor(random.choice(COLORS)),
            })
        self._t0 = time.monotonic()
        self._timer.setInterval(120 if os.environ.get("QT_REDUCED_MOTION") else 16)
        self.raise_()
        self.show()
        self._timer.start()
    def clear(self) -> None:
        self._timer.stop()
        self._parts = []
        self.hide()
    def _tick(self) -> None:
        if time.monotonic() - self._t0 >= DURATION:
            self.clear()
            self.update()
            return
        for q in self._parts:
            p, v = q["p"], q["v"]
            p.setX(p.x() + v.x())
            p.setY(p.y() + v.y())
            v.setY(v.y() + 0.34)
            v.setX(v.x() * 0.992)
            q["rot"] += q["vr"]
        self.update()
    def paintEvent(self, _event) -> None:
        if not self._parts:
            return
        fade = max(0.0, 1.0 - (time.monotonic() - self._t0) / DURATION)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for q in self._parts:
            color = QColor(q["c"])
            color.setAlphaF(fade)
            p.save()
            p.translate(q["p"])
            p.rotate(q["rot"])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(-q["w"] / 2, -q["h"] / 2, q["w"], q["h"], 1, 1)
            p.restore()

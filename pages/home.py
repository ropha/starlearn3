from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from pages.widgets import BrandMark, NextOrb
USERS = ("星月", "爸爸测试", "AI测试")
BASE_W, BASE_H = 1440, 900
class HomePage(QWidget):
    start = Signal(str)
    def __init__(self):
        super().__init__()
        self.selected = USERS[0]
        self.buttons: dict[str, QPushButton] = {}
        self.k = 1.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(21)
        lay.addStretch(2535)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setAlignment(Qt.AlignCenter)
        self.mark = BrandMark(48)
        row.addWidget(self.mark)
        self.brand = QLabel("Ai数学老师")
        self.brand.setObjectName("brandBig")
        row.addWidget(self.brand)
        lay.addLayout(row)
        pick = QHBoxLayout()
        pick.setSpacing(9)
        pick.setContentsMargins(0, 12, 0, 15)
        pick.setAlignment(Qt.AlignCenter)
        for u in USERS:
            b = QPushButton(u)
            b.setObjectName("who")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=u: self.select(name))
            pick.addWidget(b)
            self.buttons[u] = b
        lay.addLayout(pick)
        self.go = NextOrb(172)
        self.go.clicked.connect(lambda: self.start.emit(self.selected))
        lay.addWidget(self.go, 0, Qt.AlignHCenter)
        lay.addStretch(2863)
        self.select(USERS[0])
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scale()
    def _scale(self) -> None:
        k = min(max(self.width(), 1) / BASE_W, max(self.height(), 1) / BASE_H)
        sk = min(k, 1.3)
        self.k = k
        self.mark.setFixedSize(int(48 * sk), int(48 * sk))
        f = self.brand.font()
        f.setPixelSize(max(int(33 * sk), 12))
        f.setBold(False)
        self.brand.setFont(f)
        self.brand.setMinimumHeight(int(48 * sk))
        for b in self.buttons.values():
            b.setFixedHeight(max(int(29 * k), 20))
            bf = b.font()
            bf.setPixelSize(max(int(15 * sk), 9))
            bf.setBold(True)
            b.setFont(bf)
        self.go.set_scale(k)
    def select(self, user: str) -> None:
        self.selected = user
        for name, b in self.buttons.items():
            b.setProperty("on", "true" if name == user else "false")
            b.style().unpolish(b)
            b.style().polish(b)

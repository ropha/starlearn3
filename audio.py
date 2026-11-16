from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect
ROOT = Path(__file__).resolve().parent
SFX_DIR = ROOT / "assets" / "sfx"
NAMES = ("ok", "wrong", "row_ok", "row_bad", "next", "card")
_players: dict[str, QSoundEffect] = {}
_enabled = True
def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = on
def play(name: str) -> None:
    if not _enabled or name not in NAMES:
        return
    effect = _players.get(name)
    if effect is None:
        path = SFX_DIR / f"{name}.wav"
        if not path.exists():
            return
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(0.85)
        _players[name] = effect
    if effect.isPlaying():
        effect.stop()
    effect.play()

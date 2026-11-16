from __future__ import annotations
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QLineEdit, QMessageBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)
import ai
import audio
import core
import db
import keypad
import theme
import tts
from pages.card import CardOverlay
from pages.drill import OK_MS
from pages.home import HomePage
from pages.quiz import QuizPage
from pages.session_end import SessionEndPage
ROOT = Path(__file__).resolve().parent
def now() -> int:
    return int(time.time() * 1000)
class MainWindow(QWidget):
    _ai_done = Signal(dict, int)
    def __init__(self) -> None:
        super().__init__()
        self.bank = json.loads((ROOT / "bank.json").read_text(encoding="utf-8"))
        self.items = list(self.bank)
        self.store = db.Db(ROOT / "data" / "app.sqlite")
        self.brain = ai.Brain(self.bank, self.store)
        self.user = "星月"
        self.state = self.store.restore(self.user)
        self.answered: int | None = None
        self.q_index = 0
        self.q_total = 6
        self.speaker = tts.Speaker(self)
        self.speaker.failed.connect(self.on_tts_failed)
        self.speaker.ended.connect(self.on_tts_ended)
        self._tts_t0 = 0.0
        self._ai_pool = ThreadPoolExecutor(max_workers=1)
        self._ai_gen = 0
        self._ai_done.connect(self._on_ai_done)
        self.keypad = keypad.Keypad(self)
        self.keypad.btn.connect(self._on_keypad_btn)
        self._last_leds: dict[str, int] = {}
        if "--shot" not in sys.argv:
            self.keypad.start()
            QTimer.singleShot(0, self._sync_leds)
        self.stack = QStackedWidget()
        self.home = HomePage()
        self.quiz = QuizPage()
        self.speaker.segment_bright.connect(self.quiz.set_seg)
        self.session_end = SessionEndPage()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.quiz)
        self.stack.addWidget(self.session_end)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self.stack)
        self.card_overlay = CardOverlay(self)
        self.card_overlay.setGeometry(self.rect())
        self.card_overlay.hidden_done.connect(self.on_card_hidden)
        self.home.start.connect(self.on_start)
        self.quiz.pick.connect(self.on_pick)
        self.quiz.stem_click.connect(self.on_stem_click)
        self.quiz.drill_judge.connect(self.on_drill_judge)
        self.quiz.drill.row_shown.connect(self.on_drill_row_shown)
        self.quiz.next_item.connect(self.on_next)
        self.quiz.next_ready.connect(lambda: audio.play("next"))
        self.quiz.note_entered.connect(
            lambda text: self.dispatch({"type": "parent_note", "at": now(), "text": text})
        )
        self.quiz.skip.connect(self.on_skip)
        self.quiz.undo_wrong.connect(self.on_undo_wrong)
        self.quiz.quit.connect(self.on_quit)
        self.session_end.continued.connect(lambda: self.on_session_choice("继续"))
        self.session_end.ended.connect(lambda: self.on_session_choice("结束"))
        self.setWindowTitle("星月数学")
    def on_start(self, user: str) -> None:
        self.speaker.stop()
        self._ai_gen += 1
        self.user = user
        self.state = self.store.restore(user)
        if self.state.phase not in ("idle", "stopped"):
            self.state.phase = "idle"
            self.state.item = None
            self.state.feedback = None
        self.q_index = 0
        self.answered = None
        self.stack.setCurrentWidget(self.quiz)
        self.quiz.show_waiting()
        self.dispatch({"type": "start", "at": now()})
    def on_pick(self, index: int) -> None:
        if self.state.phase != "answering" or not self.state.feedback:
            return
        if self.state.feedback["_meta"]["作答结束"]:
            return
        self.dispatch({"type": "option_pick", "at": now(), "index": index})
        fb = self.state.feedback
        if fb and fb["_meta"]["作答结束"]:
            self.answered = index
            self.quiz.show_feedback(True, int(self.state.item["答案"]), index)
    def on_stem_click(self, seg: int) -> None:
        if self.state.phase == "answering" and self.state.item:
            self.quiz.set_seg(seg)
            self.dispatch({"type": "stem_click", "at": now(), "segment": seg})
    def on_drill_judge(self, yes: bool) -> None:
        if self.state.phase != "answering" or not self.state.feedback:
            return
        fb = self.state.feedback
        if fb["_meta"]["作答结束"]:
            return
        r = int(fb["_meta"].get("drillIndex", 0))
        self.dispatch({"type": "drill_judge", "at": now(), "subIndex": r, "成立判断": yes})
    def on_drill_row_shown(self, row: int) -> None:
        if (
            self.state.phase == "answering"
            and self.state.item
            and self.state.item.get("题型") == "drill"
        ):
            self.dispatch({"type": "drill_row_shown", "at": now(), "subIndex": row})
    def on_next(self) -> None:
        if self.quiz._next_delay:
            return
        if self.quiz._card_lock:
            return
        self.answered = None
        self.dispatch({"type": "next", "at": now()})
    def on_card_hidden(self) -> None:
        self.quiz._card_lock = False
        if (
            self.state.phase == "answering"
            and self.state.feedback
            and self.state.feedback["_meta"]["作答结束"]
            and self.state.item is not None
        ):
            self.quiz.unlock_next()
    def on_skip(self, reason: str) -> None:
        if self.state.phase != "answering":
            return
        self.answered = None
        self.dispatch({"type": "skip", "at": now(), "reason": reason})
    def on_undo_wrong(self) -> None:
        self.quiz._clear_flash()
        self.dispatch({"type": "undo_wrong", "at": now()})
    def on_quit(self) -> None:
        self._ai_gen += 1
        self.speaker.stop()
        self.quiz.hud.stop()
        self.quiz.hide_waiting()
        if self.state.phase not in ("idle", "stopped"):
            self.state.phase = "idle"
            self.state.item = None
            self.state.feedback = None
        self.stack.setCurrentWidget(self.home)
    def on_session_choice(self, choice: str) -> None:
        self.dispatch({"type": "session_choice", "at": now(), "选择": choice})
    def _show_timeline(self) -> None:
        start = self.state.session_start or 0
        cards = []
        for c in self.store.cards(self.user):
            d = dict(c)
            d["is_new"] = bool(start and int(c.get("at") or 0) >= start)
            cards.append(d)
        self.session_end.render(cards)
        self.stack.setCurrentWidget(self.session_end)
    def on_parent_key(self, n: int) -> None:
        if self.state.phase == "answering" and self.state.feedback:
            self.dispatch({"type": "parent_key", "at": now(), "key": n})
    def on_speak_stem(self, e: dict) -> None:
        item = e.get("item") or self.state.item
        if not item:
            return
        seg = e.get("segment")
        parts = core.stem_segments(item)
        if parts:
            chosen = [parts[0], parts[1]] if seg is None else [parts[int(seg)]]
        else:
            chosen = [str(item.get("题干") or "")]
        chosen = [p for p in chosen if p]
        if not chosen:
            return
        self.quiz.set_seg(0 if seg is None else int(seg))
        self._tts_t0 = time.monotonic()
        self.speaker.speak_parts(chosen)
    def on_tts_failed(self, msg: str) -> None:
        self._finish_tts(0)
    def on_tts_ended(self) -> None:
        ms = int((time.monotonic() - self._tts_t0) * 1000) if self._tts_t0 else 0
        self._finish_tts(ms)
    def _finish_tts(self, ms: int) -> None:
        if self.state.phase == "answering" and self.state.feedback:
            self.dispatch({"type": "tts_ended", "at": now(), "朗读时长": ms})
    def _test_card(self) -> None:
        self.speaker.stop()
        self.quiz.hud.stop()
        self.card_overlay.hide()
        nodes = [
            ("kp-addsub-5", "初识"), ("kp-addsub-5", "在练"),
            ("kp-addsub-10", "熟练"), ("kp-addsub-10", "进阶"),
        ]
        idx = getattr(self, "_test_card_idx", -1) + 1
        self._test_card_idx = idx
        node, tier = nodes[idx % len(nodes)]
        self.apply({"type": "card", "card": {"node": node, "tier": tier}})
    def _test_gallery(self, n: int = 0) -> None:
        self.speaker.stop()
        self.quiz.hud.stop()
        self.card_overlay.hide()
        cards = []
        if n > 0:
            nodes = [
                ("kp-addsub-5", "初识"), ("kp-addsub-5", "在练"),
                ("kp-addsub-10", "熟练"), ("kp-addsub-10", "进阶"),
            ]
            base = now()
            cards = [
                {"node": nodes[i % 4][0], "tier": nodes[i % 4][1],
                 "at": base - (n - i) * 86400000, "is_new": i == n - 1}
                for i in range(n)
            ]
        else:
            try:
                cards = [dict(c) for c in self.store.cards(self.user)]
            except Exception:
                pass
            if not cards:
                t = now()
                cards = [
                    {"node": "kp-addsub-5", "tier": "初识", "at": t - 20 * 86400000, "is_new": False},
                    {"node": "kp-addsub-5", "tier": "在练", "at": t - 7 * 86400000, "is_new": False},
                    {"node": "kp-addsub-10", "tier": "初识", "at": t, "is_new": True},
                ]
            else:
                cards[-1] = dict(cards[-1], is_new=True)
        self.session_end.render(cards)
        self.stack.setCurrentWidget(self.session_end)
    def _test_back(self) -> None:
        self.card_overlay.hide()
        self.stack.setCurrentWidget(self.quiz if self.state.item else self.home)
    def _on_keypad_btn(self, key: str, down: bool) -> None:
        if down:
            self._handle_keypad(key)
    def _sync_leds(self) -> None:
        s = self.state
        valid: set[str] = set()
        if (
            s.phase == "answering"
            and s.item
            and s.feedback
            and not s.feedback["_meta"]["作答结束"]
        ):
            if s.item.get("题型") == "drill":
                valid = {"C", "D"}
            else:
                valid = set("ABCD"[: min(4, len(s.item.get("选项") or []))])
        n = 0
        if s.phase == "idle":
            n = 1
        elif s.phase == "stopped":
            n = 2
        elif s.phase == "answering" and s.feedback and s.feedback["_meta"]["作答结束"]:
            n = 2
        intent = {k: (1 if k in valid else 0) for k in "ABCD"}
        intent["N"] = n
        if intent == self._last_leds:
            return
        self._last_leds = intent
        for k, v in intent.items():
            self.keypad.set_led(k, v)
    def _handle_keypad(self, key: str) -> bool:
        if key == "N":
            if self.state.phase == "idle":
                self.on_start(self.user)
                return True
            if self.state.phase == "stopped":
                self.on_session_choice("继续")
                return True
            if (
                self.state.phase == "answering"
                and self.state.feedback
                and self.state.feedback["_meta"]["作答结束"]
            ):
                if self.quiz._card_lock:
                    return False
                self.on_next()
                return True
            return False
        if self.state.phase != "answering" or not self.state.item or not self.state.feedback:
            return False
        if self.state.feedback["_meta"]["作答结束"]:
            return False
        item = self.state.item
        if item.get("题型") == "drill":
            if key == "C":
                self.on_drill_judge(True)
                return True
            if key == "D":
                self.on_drill_judge(False)
                return True
            return False
        idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(key)
        if idx is None or idx >= len(item.get("选项") or []):
            return False
        self.on_pick(idx)
        return True
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and not isinstance(obj, (QLineEdit, QTextEdit)):
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.state.phase == "answering" and self.state.item:
                    self.quiz.show_note()
                    return True
            if ev.key() in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5):
                self.on_parent_key(ev.key() - Qt.Key_0)
                return True
            if ev.key() in (Qt.Key_A, Qt.Key_B, Qt.Key_C, Qt.Key_D, Qt.Key_N):
                self._handle_keypad(chr(ev.key()))
                return True
            if ev.key() == Qt.Key_F8:
                self._test_card()
                return True
            if ev.key() == Qt.Key_F9:
                self._test_gallery()
                return True
            if ev.key() == Qt.Key_F10:
                self._test_back()
                return True
        return super().eventFilter(obj, ev)
    def dispatch(self, ev: dict) -> None:
        self.state, effects = core.reduce(self.state, ev)
        self.store.append(self.user, ev)
        for e in effects:
            self.apply(e)
        self.store.maybe_snapshot(self.user, self.state)
        self._sync_leds()
    def apply(self, e: dict) -> None:
        kind = e["type"]
        if kind == "request_items":
            opening = bool(e.get("opening"))
            self._ai_gen += 1
            gen = self._ai_gen
            self.quiz.show_waiting()
            ctx = {
                "user": self.user,
                "model": self.state.model,
                "items": self.items,
                "n": 6,
                "opening": opening,
            }
            self._ai_pool.submit(self._decide_worker, ctx, gen)
        elif kind == "speak_stem":
            self.on_speak_stem(e)
        elif kind == "show_item":
            self.stack.setCurrentWidget(self.quiz)
            if e.get("drillIndex") is not None:
                row = int(e["drillIndex"])
                if row == 0:
                    self.q_index += 1
                    self.quiz.render(e["item"], self.q_index, self.q_total)
                else:
                    prev = e["item"]["选项"][row - 1]
                    self.quiz.drill.mark_ok(bool(prev["成立"]))
                    QTimer.singleShot(OK_MS, lambda it=e["item"], rw=row: self.quiz.render_drill(it, rw))
                return
            self.q_index += 1
            self.quiz.render(e["item"], self.q_index, self.q_total)
        elif kind == "persist_feedback":
            self.store.save_model(self.user, self.state.model)
            if self.state.cards:
                self.store.add_cards(self.user, self.state.cards)
        elif kind == "parent_badge":
            fb = self.state.feedback
            if fb and self.state.item:
                self.quiz.hud.set_parent(
                    e["key"], fb["家长数据"],
                    self.state.item.get("难度分数"), self.state.item.get("预测答题时长"),
                )
        elif kind == "play_sfx":
            audio.play(e["name"])
            if e["name"] == "row_ok" and self.state.item:
                self.quiz.celebrate_drill_row(self.state.item, int(e.get("row", 0)))
                self.keypad.celebrate()
            elif e["name"] == "ok" and self.state.item:
                if self.state.item.get("题型") != "drill":
                    ans = self.state.item.get("答案")
                    if isinstance(ans, int):
                        self.quiz.celebrate(ans)
                        self.keypad.celebrate()
        elif kind == "neutral_rechoose":
            if e.get("drill"):
                self.quiz.drill.flash_wrong(bool(e.get("yes")))
                self.quiz.btn_undo.show()
            else:
                self.quiz.flash_wrong(int(e["index"]))
        elif kind == "show_correct":
            if self.state.item and self.state.item.get("题型") == "drill":
                last = self.state.item["选项"][-1]
                self.quiz.drill.mark_ok(bool(last["成立"]))
                self.quiz.show_feedback(True, 0, 0)
        elif kind == "card":
            audio.play("card")
            c = e.get("card") or {}
            self.quiz.lock_next_for_card()
            self.card_overlay.show_card(str(c.get("node") or ""), str(c.get("tier") or ""))
        elif kind == "session_stop":
            self.quiz.hud.stop()
            self.speaker.stop()
            self._show_timeline()
        elif kind == "items_exhausted":
            self.quiz.hud.stop()
            self._show_timeline()
        elif kind == "session_end":
            self.quiz.hud.stop()
            self.stack.setCurrentWidget(self.home)
    def _decide_worker(self, ctx: dict, gen: int) -> None:
        try:
            decision, _ok, _err = self.brain.decide(ctx)
        except Exception:
            decision = {"items": [], "预测时长": {}, "档位": {}, "发卡": [], "理由": "decide-crash"}
        self._ai_done.emit(decision, gen)
    def _on_ai_done(self, decision: dict, gen: int) -> None:
        if gen != self._ai_gen:
            return
        self.state.model = core.apply_ai(self.state.model, decision)
        by_id = {i["id"]: i for i in self.items}
        picked: list[dict] = []
        for iid in decision["items"]:
            item = by_id.get(iid)
            if item is None:
                continue
            pred = (decision.get("预测时长") or {}).get(iid)
            if pred is not None:
                item = dict(item, 预测答题时长=pred)
            picked.append(item)
        if not picked:
            self.dispatch({"type": "items_exhausted", "at": now()})
            return
        self.q_total = max(len(picked), 1)
        self.q_index = 0
        self.dispatch({"type": "items_received", "at": now(), "items": picked})
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.card_overlay.setGeometry(self.rect())
    def closeEvent(self, event) -> None:
        self.keypad.stop()
        self.speaker.close()
        self.store.close()
        super().closeEvent(event)
def _install_crash_handler() -> None:
    def hook(exc_type, exc, tb, dialog: bool = True) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            p = ROOT / "data" / "error.log"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(time.strftime("[%Y-%m-%d %H:%M:%S]\n") + text + "\n")
        except OSError:
            pass
        sys.stderr.write(text)
        if not dialog:
            return
        try:
            QMessageBox.critical(
                None, "程序出错",
                f"已记录到 data/error.log\n\n{exc_type.__name__}: {exc}",
            )
        except Exception:
            pass
    sys.excepthook = hook
    def thread_hook(args) -> None:
        hook(args.exc_type, args.exc_value, args.exc_traceback, dialog=False)
    threading.excepthook = thread_hook
def main() -> int:
    app = QApplication(sys.argv)
    _install_crash_handler()
    font_file = ROOT / "assets" / "fonts" / "NotoSansSC-VF.ttf"
    font_id = QFontDatabase.addApplicationFont(str(font_file)) if font_file.exists() else -1
    if font_id < 0 or theme.FONT_STEM not in QFontDatabase.families():
        theme.FONT_STEM = theme.FONT
    app.setStyleSheet(theme.QSS)
    win = MainWindow()
    app.installEventFilter(win)
    if "--shot" in sys.argv:
        if win.speaker.tts:
            win.speaker.tts.close()
        win.speaker.cfg = None
        win.speaker.tts = None
        win.resize(1440, 900)
        win.show()
    else:
        win.showFullScreen()
        print("快捷键：F8 发猫卡 / F9 结束画廊 / F10 返回", flush=True)
    if "--card" in sys.argv:
        QTimer.singleShot(400, win._test_card)
    if "--gallery" in sys.argv:
        QTimer.singleShot(400, win._test_gallery)
    if "--gallery100" in sys.argv:
        QTimer.singleShot(400, lambda: win._test_gallery(100))
    if "--shot" in sys.argv:
        def snap(name):
            pix = QPixmap(win.size())
            pix.fill()
            win.render(pix)
            pix.save(str(ROOT / name))
            print(name)
        QTest.qWait(300)
        snap("shot-home.png")
        win.on_start("AI测试")
        QTest.qWait(600)
        snap("shot-quiz.png")
        if win.state.item:
            win.on_pick((win.state.item["答案"] + 1) % 4)
            QTest.qWait(120)
            snap("shot-wrong-flash.png")
            win.on_pick(win.state.item["答案"])
            QTest.qWait(400)
            snap("shot-feedback.png")
            win.quiz._open_skip()
            QTest.qWait(200)
            snap("shot-skip-modal.png")
            win.quiz._close_skip()
        pic = next((i for i in win.items if i["题型"] == "picture"), None)
        if pic:
            win.quiz.render(pic, 1, 6)
            QTest.qWait(400)
            snap("shot-pic.png")
        drill = next((i for i in win.items if i["题型"] == "drill"), None)
        if drill:
            win.quiz.render(drill, 1, 6)
            QTest.qWait(300)
            snap("shot-drill.png")
            first_ok = bool(drill["选项"][0]["成立"])
            win.quiz.drill.mark_ok(first_ok)
            QTest.qWait(120)
            snap("shot-drill-ok.png")
            win.quiz.drill.render(drill, 0)
            win.quiz.drill.flash_wrong(not first_ok)
            QTest.qWait(120)
            snap("shot-drill-wrong.png")
            win.quiz.celebrate_drill(drill)
            QTest.qWait(260)
            snap("shot-drill-celebrate.png")
            win.quiz.confetti.clear()
        if win.state.item:
            win.state.item["难度分数"] = 3
            win.state.item["预测答题时长"] = 4
        win.quiz.hud.set_item(3, 4, now())
        win.quiz.hud.freeze(0.86)
        snap("shot-hud-base.png")
        for n in range(1, 6):
            if n == 1:
                QTest.keyClick(win, Qt.Key_1)
            else:
                win.on_parent_key(n)
            QTest.qWait(60)
            snap(f"shot-hud-key{n}.png")
        win.card_overlay.show_card("kp-addsub-5", "初识")
        QTest.qWait(180)
        snap("shot-card-reveal.png")
        QTest.qWait(500)
        snap("shot-card.png")
        win.card_overlay.hide()
        demo = [
            {"node": "kp-addsub-5", "tier": "初识", "at": now() - 20 * 86400000, "is_new": False},
            {"node": "kp-addsub-5", "tier": "在练", "at": now() - 7 * 86400000, "is_new": False},
            {"node": "kp-addsub-10", "tier": "初识", "at": now(), "is_new": True},
        ]
        win.session_end.render(demo)
        win.stack.setCurrentWidget(win.session_end)
        QTest.qWait(300)
        snap("shot-session-end.png")
        return 0
    return app.exec()
if __name__ == "__main__":
    sys.exit(main())

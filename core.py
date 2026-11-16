from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
Item = dict[str, Any]
Feedback = dict[str, Any]
Event = dict[str, Any]
Effect = dict[str, Any]
AUTO_SUBMIT_SECONDS = 20
SESSION_SECONDS = 15 * 60
TIERS = (1, 2, 3)
CYCLE = ("应用题",) * 5 + ("口算",)
TIER_NAMES = ("未开", "初识", "在练", "熟练", "进阶")
CLEAN_TAGS = ("分心了", "家长帮解答", "家长帮回神", "题面措辞导致脑超载", "题面不清晰")
@dataclass
class State:
    user: str = "星月"
    phase: str = "idle"
    item: Item | None = None
    feedback: Feedback | None = None
    pool: list[Item] = field(default_factory=list)
    pending: list[Feedback] = field(default_factory=list)
    history: list[list[Feedback]] = field(default_factory=list)
    session_start: int | None = None
    answer_started_at: int | None = None
    task_20s: int | None = None
    next_at: int | None = None
    today_total: int = 0
    today_score: int = 0
    cards: list[dict] = field(default_factory=list)
    model: dict = field(default_factory=dict)
    message: str = ""
def new_feedback(item: Item, at: int) -> Feedback:
    return {
        "题": item,
        "用户数据": {
            "首答对错": None,
            "重选次数": 0,
            "重听次数": 0,
            "答题时长": None,
            "朗读时长": None,
            "跳过原因": None,
        },
        "家长数据": {
            "在努力": False,
            "分心了": False,
            "家长帮解答": False,
            "家长帮回神": False,
            "题面措辞导致脑超载": False,
            "题面不清晰": False,
            "难度分数修正": None,
            "预测答题时长修正": None,
        },
        "_meta": {
            "作答结束": False,
            "已提交": False,
            "答题时长作废": False,
            "drillIndex": 0,
            "drillRows": [],
            "subRows": [],
            "subDone": [],
            "subStartedAt": [],
        },
        "时间戳": {"出示": at, "作答": None, "反馈落定": None},
    }
def judge(item: Item, selected: int | None) -> bool:
    if selected is None:
        return False
    if item.get("题型") == "drill":
        return False
    return selected == item.get("答案")
def judge_drill(item: Item, rows: list[bool]) -> bool:
    opts = item.get("选项") or []
    return len(rows) == len(opts) and all(bool(r) == bool(o.get("成立")) for r, o in zip(rows, opts))
def expected_rows(item: Item) -> list[bool]:
    return [bool(o.get("成立")) for o in item.get("选项") or []]
_COND = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
         "０", "１", "２", "３", "４", "５", "６", "７", "８", "９", "几", "多少")
def stem_segments(item: Item) -> tuple[str, str] | None:
    explicit = item.get("题干分段")
    if isinstance(explicit, (list, tuple)) and len(explicit) == 2 and explicit[0] and explicit[1]:
        return (str(explicit[0]), str(explicit[1]))
    parts = [p.strip() for p in _split_sentences(str(item.get("题干") or "")) if p.strip()]
    if len(parts) < 3:
        return None
    at = next((i for i, p in enumerate(parts) if any(c in p for c in _COND)), -1)
    if at <= 0:
        return None
    return ("".join(parts[:at]), "".join(parts[at:]))
def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？":
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out
def kp_of(item: Item) -> str:
    return "口算" if item.get("题型") == "drill" or item.get("主题") == "口算" else "应用题"
def tier_of(model: dict, kp: str) -> int:
    return int((model.get("档") or {}).get(kp) or 1)
def pick(
    items: list[Item],
    model: dict,
    n: int,
    exclude: set[str] | None = None,
    opening: bool = False,
) -> list[Item]:
    seen = set(model.get("见过") or [])
    ban = set(model.get("隔离") or []) | (exclude or set())
    usable = [i for i in items if i.get("id") not in ban]
    picked: list[Item] = []
    used: set[str] = set()
    kp_tier = {"应用题": tier_of(model, "应用题"), "口算": tier_of(model, "口算")}
    pos = 0 if opening else int(model.get("轮位") or 0) % len(CYCLE)
    def fresh(kp: str, tier: int) -> list[Item]:
        return [
            i
            for i in usable
            if kp_of(i) == kp and int(i.get("难度分数") or 1) == tier and i.get("id") not in seen and i.get("id") not in used
        ]
    def by_pri(xs: list[Item]) -> list[Item]:
        return sorted(xs, key=lambda i: -int(i.get("优先级值") or 0))
    for _ in range(n * len(CYCLE)):
        if len(picked) >= n:
            break
        kp = CYCLE[pos]
        pos = (pos + 1) % len(CYCLE)
        tier = kp_tier[kp]
        got = by_pri(fresh(kp, tier))
        if not got:
            for t in range(tier - 1, 0, -1):
                got = by_pri(fresh(kp, t))
                if got:
                    break
        if not got:
            for t in range(tier + 1, max(TIERS) + 1):
                got = by_pri(fresh(kp, t))
                if got:
                    break
        if not got:
            continue
        item = got[0]
        picked.append(item)
        used.add(item["id"])
    model["轮位"] = pos
    return picked
def remaining(items: list[Item], model: dict) -> int:
    seen = set(model.get("见过") or [])
    ban = set(model.get("隔离") or [])
    return sum(1 for i in items if i.get("id") not in seen and i.get("id") not in ban)
def is_clean(fb: Feedback) -> bool:
    parent = fb.get("家长数据") or {}
    user = fb.get("用户数据") or {}
    meta = fb.get("_meta") or {}
    if any(bool(parent.get(k)) for k in CLEAN_TAGS):
        return False
    if (user.get("重听次数") or 0) > 0:
        return False
    if not meta.get("作答结束") or user.get("跳过原因"):
        return False
    return (user.get("答题时长") or 0) > 0
def absorb(model: dict, fb: Feedback) -> dict:
    model = dict(model)
    item = fb.get("题") or {}
    iid = item.get("id")
    seen = list(model.get("见过") or [])
    if iid and iid not in seen:
        seen.append(iid)
    model["见过"] = seen
    isolated = list(model.get("隔离") or [])
    parent = fb.get("家长数据") or {}
    if (parent.get("题面措辞导致脑超载") or parent.get("题面不清晰")) and iid and iid not in isolated:
        isolated.append(iid)
    model["隔离"] = isolated
    if is_clean(fb):
        kp = kp_of(item)
        tier = int(item.get("难度分数") or 1)
        key = f"{kp}|{tier}"
        samples = dict(model.get("样本") or {})
        row = {"t": fb["用户数据"]["答题时长"], "at": fb["时间戳"].get("作答") or 0, "id": iid, "pred": item.get("预测答题时长") or 8}
        samples[key] = (list(samples.get(key) or []) + [row])[-200:]
        model["样本"] = samples
    return model
def fast_rise(model: dict, fb: Feedback, ratio: float = 0.4, n: int = 2) -> str | None:
    if not is_clean(fb):
        return None
    item = fb.get("题") or {}
    kp = kp_of(item)
    tier = tier_of(model, kp)
    rows = (model.get("样本") or {}).get(f"{kp}|{tier}") or []
    recent = rows[-n:]
    if len(recent) < n:
        return None
    if all(r["t"] <= (r.get("pred") or 8) * ratio for r in recent):
        return kp
    return None
def set_tier(model: dict, kp: str, to: int) -> dict:
    to = max(TIERS[0], min(TIERS[-1], int(to)))
    model = dict(model)
    tiers = dict(model.get("档") or {})
    if tiers.get(kp) != to:
        tiers[kp] = to
        model["档"] = tiers
    return model
def award(model: dict, fb: Feedback) -> list[dict]:
    item = fb.get("题") or {}
    node = item.get("知识点") or item.get("知识格") or ""
    if not node or not is_clean(fb):
        return []
    owned = {c.get("tier") for c in (model.get("cats") or []) if c.get("node") == node}
    kp = kp_of(item)
    tier = tier_of(model, kp)
    n = sum(1 for r in (model.get("样本") or {}).get(f"{kp}|{tier}", []) if r.get("at"))
    if "初识" not in owned and n >= 3:
        return [{"node": node, "tier": "初识", "at": fb["时间戳"].get("作答") or 0, "source": "rule"}]
    return []
AI_SCHEMA = {
    "items": "题目 id 列表",
    "预测时长": "id -> 秒",
    "档位": "应用题/口算 -> 1..3",
    "发卡": "[{node,tier}]",
    "理由": "字符串",
}
def validate_ai(decision: dict, items: list[Item]) -> tuple[dict, list[str]]:
    errors: list[str] = []
    by_id = {i["id"]: i for i in items}
    ids = [i for i in (decision.get("items") or []) if i in by_id]
    if len(ids) != len(decision.get("items") or []):
        errors.append("unknown_item")
    tiers = decision.get("档位") or {}
    for kp, t in tiers.items():
        if kp not in ("应用题", "口算") or not isinstance(t, int) or t not in TIERS:
            errors.append(f"bad_tier:{kp}")
    pred = decision.get("预测时长") or {}
    for iid, sec in pred.items():
        if iid not in by_id or not isinstance(sec, (int, float)) or not (3 <= sec <= 60):
            errors.append(f"bad_pred:{iid}")
    clean = {"items": ids, "预测时长": {k: v for k, v in pred.items() if k in by_id}, "档位": {k: v for k, v in tiers.items() if k in ("应用题", "口算") and v in TIERS}, "发卡": decision.get("发卡") or [], "理由": decision.get("理由") or ""}
    return clean, errors
def apply_ai(model: dict, decision: dict) -> dict:
    model = dict(model)
    for kp, t in (decision.get("档位") or {}).items():
        if kp in ("应用题", "口算") and isinstance(t, int) and t in TIERS:
            model = set_tier(model, kp, t)
    return model
def reduce(s: State, ev: Event) -> tuple[State, list[Effect]]:
    kind = ev.get("type")
    at = int(ev.get("at") or 0)
    effects: list[Effect] = []
    match kind:
        case "start":
            s = State(user=s.user, today_total=s.today_total, today_score=s.today_score, model=s.model)
            s.phase = "waiting"
            s.session_start = at
            effects.append({"type": "request_items", "opening": True})
        case "items_received":
            s = State(**s.__dict__)
            items = ev.get("items") or []
            if s.phase == "answering":
                s.pool = s.pool + list(items)
            else:
                s.pool = list(items)
                if not s.pool and s.phase == "waiting":
                    s.phase = "stopped"
                    effects.append({"type": "items_exhausted"})
                elif s.phase == "waiting":
                    s, more = show(s, at)
                    effects += more
        case "option_pick":
            if s.phase != "answering" or not s.item or not s.feedback:
                return (s, effects)
            if s.item.get("题型") == "drill":
                return (s, effects)
            if s.feedback["_meta"]["作答结束"]:
                return (s, effects)
            ok = judge(s.item, int(ev.get("index", -1)))
            s = State(**s.__dict__)
            s.feedback = _clone(s.feedback)
            first = s.feedback["用户数据"]["首答对错"] is None
            if first:
                s.feedback["用户数据"]["首答对错"] = ok
            else:
                s.feedback["用户数据"]["重选次数"] += 1
            s.feedback["用户数据"]["答题时长"] = round((at - (s.answer_started_at or at)) / 1000, 2)
            if ok:
                s.feedback["_meta"]["作答结束"] = True
                s.feedback["时间戳"]["作答"] = at
                effects.append({"type": "play_sfx", "name": "ok"})
                effects.append({"type": "show_correct", "index": None})
            else:
                effects.append({"type": "play_sfx", "name": "wrong"})
                effects.append({"type": "neutral_rechoose", "index": int(ev.get("index", -1))})
        case "drill_row_shown":
            if s.phase == "answering" and s.feedback and s.item and s.item.get("题型") == "drill":
                r = int(ev.get("subIndex") or 0)
                meta = s.feedback["_meta"]
                starts = list(meta.get("subStartedAt") or [])
                while len(starts) <= r:
                    starts.append(None)
                if starts[r] is None:
                    s = State(**s.__dict__)
                    s.feedback = _clone(s.feedback)
                    s.feedback["_meta"]["subStartedAt"] = starts
                    s.feedback["_meta"]["subStartedAt"][r] = at
        case "drill_judge":
            if s.phase != "answering" or not s.item or not s.feedback:
                return (s, effects)
            if s.item.get("题型") != "drill":
                return (s, effects)
            fb = _clone(s.feedback)
            meta = fb["_meta"]
            if meta.get("作答结束"):
                return (s, effects)
            opts = s.item.get("选项") or []
            n = len(opts)
            r = int(ev.get("subIndex", meta.get("drillIndex", 0)))
            if r != int(meta.get("drillIndex", 0)):
                return (s, effects)
            subs = list(meta.get("subRows") or [])
            done = list(meta.get("subDone") or [])
            while len(subs) < n:
                subs.append({"首答对错": None, "重选次数": 0, "答题时长": None})
            while len(done) < n:
                done.append(False)
            if done[r]:
                return (s, effects)
            want = bool(opts[r].get("成立"))
            ok = bool(ev.get("成立判断")) == want
            first = subs[r]["首答对错"] is None
            if first:
                subs[r]["首答对错"] = ok
            else:
                subs[r]["重选次数"] += 1
            meta["subRows"] = subs
            meta["subDone"] = done
            s = State(**s.__dict__)
            s.feedback = fb
            if not ok:
                effects.append({"type": "play_sfx", "name": "wrong"})
                effects.append({"type": "neutral_rechoose", "index": r, "drill": True, "yes": bool(ev.get("成立判断"))})
                return (s, effects)
            starts = list(meta.get("subStartedAt") or [])
            t0 = starts[r] if r < len(starts) and starts[r] else (s.answer_started_at or at)
            subs[r]["答题时长"] = round((at - t0) / 1000, 2)
            rows = list(meta.get("drillRows") or [])
            while len(rows) <= r:
                rows.append(False)
            rows[r] = True
            done[r] = True
            meta["subRows"] = subs
            meta["subDone"] = done
            meta["drillRows"] = rows
            effects.append({"type": "play_sfx", "name": "row_ok", "row": r})
            if all(done):
                fb["用户数据"]["首答对错"] = all(x["首答对错"] is True for x in subs)
                fb["用户数据"]["答题时长"] = round(sum(x["答题时长"] or 0 for x in subs), 2)
                fb["用户数据"]["重选次数"] = sum(x["重选次数"] for x in subs)
                fb["_meta"]["作答结束"] = True
                fb["时间戳"]["作答"] = at
                effects.append({"type": "play_sfx", "name": "ok" if fb["用户数据"]["首答对错"] else "wrong"})
                effects.append({"type": "show_correct", "index": None})
            else:
                meta["drillIndex"] = r + 1
                effects.append({"type": "show_item", "item": s.item, "drillIndex": r + 1})
        case "tts_ended":
            if s.feedback:
                s = State(**s.__dict__)
                s.feedback = _clone(s.feedback)
                s.feedback["用户数据"]["朗读时长"] = ev.get("朗读时长")
        case "stem_click":
            if s.item:
                seg = ev.get("segment")
                effects.append({"type": "speak_stem", "item": s.item, "segment": seg})
                if s.feedback and not s.feedback["_meta"]["作答结束"]:
                    s = State(**s.__dict__)
                    s.feedback = _clone(s.feedback)
                    s.feedback["用户数据"]["重听次数"] += 1
        case "parent_note":
            if s.feedback:
                text = str(ev.get("text") or "").strip()
                if text:
                    s = State(**s.__dict__)
                    s.feedback = _clone(s.feedback)
                    notes = s.feedback["家长数据"].setdefault("备注", [])
                    notes.append({"at": int(ev.get("at") or 0), "text": text})
        case "parent_key":
            if s.feedback:
                s = State(**s.__dict__)
                s.feedback = _clone(s.feedback)
                key = int(ev.get("key") or 0)
                P = s.feedback["家长数据"]
                if key == 1:
                    cur = P.get("难度分数修正")
                    P["难度分数修正"] = -1 if cur is None else (1 if cur == -1 else None)
                elif key == 3:
                    cur = P.get("预测答题时长修正")
                    P["预测答题时长修正"] = -1 if cur is None else (1 if cur == -1 else None)
                elif key == 2:
                    trying, away = bool(P.get("在努力")), bool(P.get("分心了"))
                    P["在努力"] = not trying and not away
                    P["分心了"] = trying
                elif key == 4:
                    oload, unclear = bool(P.get("题面措辞导致脑超载")), bool(P.get("题面不清晰"))
                    P["题面措辞导致脑超载"] = not oload and not unclear
                    P["题面不清晰"] = oload
                elif key == 5:
                    helped, refocus = bool(P.get("家长帮解答")), bool(P.get("家长帮回神"))
                    P["家长帮解答"] = not helped and not refocus
                    P["家长帮回神"] = helped
                effects.append({"type": "parent_badge", "key": key})
        case "auto_submit_20s":
            return (s, effects)
        case "skip":
            if s.phase != "answering":
                return (s, effects)
            s, effects = finish(s, at, effects, skipped=str(ev.get("reason") or "跳过"))
            s, effects = commit(s, at, effects)
            if s.session_start is not None and at - s.session_start >= SESSION_SECONDS * 1000:
                s.phase = "stopped"
                effects.append({"type": "session_stop"})
                return (s, effects)
            if s.pool:
                s, more = show(s, at)
                effects += more
            else:
                s.phase = "waiting"
                effects.append({"type": "request_items", "opening": False})
        case "undo_wrong":
            if s.phase == "answering" and s.feedback:
                meta = s.feedback["_meta"]
                wrong = s.feedback["用户数据"]["首答对错"] is False or any(
                    row.get("首答对错") is False for row in (meta.get("subRows") or [])
                )
            else:
                wrong = False
            if wrong and not s.feedback["_meta"]["已提交"]:
                s = State(**s.__dict__)
                fb = _clone(s.feedback)
                fb["用户数据"]["首答对错"] = None
                fb["用户数据"]["重选次数"] += 1
                fb["用户数据"]["答题时长"] = None
                fb["_meta"]["作答结束"] = False
                fb["_meta"]["drillRows"] = []
                fb["_meta"]["drillIndex"] = 0
                fb["_meta"]["subRows"] = []
                fb["_meta"]["subDone"] = []
                fb["_meta"]["subStartedAt"] = []
                fb["时间戳"]["作答"] = None
                s.feedback = fb
                effects.append({"type": "show_item", "item": s.item})
        case "next":
            if s.phase != "answering" or not s.feedback:
                return (s, effects)
            if not s.feedback["_meta"]["作答结束"]:
                return (s, effects)
            s, effects = commit(s, at, effects)
            if s.session_start is not None and at - s.session_start >= SESSION_SECONDS * 1000:
                s.phase = "stopped"
                effects.append({"type": "session_stop"})
                return (s, effects)
            if s.pool:
                s, more = show(s, at)
                effects += more
            else:
                s.phase = "waiting"
                effects.append({"type": "request_items", "opening": False})
        case "items_exhausted":
            if s.phase in ("answering", "waiting"):
                s.phase = "stopped"
                effects.append({"type": "session_stop"})
        case "session_choice":
            if s.phase != "stopped":
                return (s, effects)
            if (
                s.feedback
                and s.feedback["_meta"].get("作答结束")
                and not s.feedback["_meta"].get("已提交")
            ):
                s, effects = commit(s, at, effects)
            if str(ev.get("选择") or "继续") == "结束":
                s = State(**s.__dict__)
                s.phase = "idle"
                s.item = None
                s.feedback = None
                s.pool = []
                s.session_start = None
                effects.append({"type": "session_end"})
                return (s, effects)
            s = State(**s.__dict__)
            s.phase = "waiting"
            s.item = None
            s.feedback = None
            s.session_start = at
            s.cards = []
            if s.pool:
                s, more = show(s, at)
                effects += more
            else:
                effects.append({"type": "request_items", "opening": False})
        case "close_session":
            s.phase = "idle"
            s.item = None
            s.feedback = None
            s.pool = []
            s.session_start = None
            effects.append({"type": "session_end"})
    return (s, effects)
def show(s: State, at: int) -> tuple[State, list[Effect]]:
    if not s.pool:
        s = State(**s.__dict__)
        s.phase = "waiting"
        return (s, [{"type": "request_items", "opening": False}])
    s = State(**s.__dict__)
    s.item = s.pool[0]
    s.pool = s.pool[1:]
    s.feedback = new_feedback(s.item, at)
    s.phase = "answering"
    s.answer_started_at = at
    s.task_20s = at + AUTO_SUBMIT_SECONDS * 1000
    s.next_at = None
    if s.item.get("题型") == "drill":
        effects: list[Effect] = [
            {"type": "show_item", "item": s.item, "drillIndex": 0},
            {"type": "start_20s", "deadline": s.task_20s},
        ]
    else:
        effects: list[Effect] = [
            {"type": "show_item", "item": s.item},
            {"type": "speak_stem", "item": s.item, "segment": None},
            {"type": "start_20s", "deadline": s.task_20s},
        ]
    return (s, effects)
def finish(s: State, at: int, effects: list[Effect], skipped: str | None = None) -> tuple[State, list[Effect]]:
    s = State(**s.__dict__)
    fb = _clone(s.feedback)
    fb["用户数据"]["跳过原因"] = skipped
    fb["_meta"]["作答结束"] = True
    fb["时间戳"]["作答"] = at
    if fb["用户数据"]["答题时长"] is None:
        fb["用户数据"]["答题时长"] = round((at - (s.answer_started_at or at)) / 1000, 2)
    s.feedback = fb
    effects.append({"type": "cancel_20s"})
    return (s, effects)
def commit(s: State, at: int, effects: list[Effect]) -> tuple[State, list[Effect]]:
    s = State(**s.__dict__)
    fb = _clone(s.feedback)
    fb["_meta"]["已提交"] = True
    fb["时间戳"]["反馈落定"] = at
    s.pending = s.pending + [fb]
    s.history = (s.history + [[fb]])[-3:]
    s.today_total += 1
    if fb["用户数据"].get("首答对错"):
        s.today_score += 1
    model = absorb(s.model, fb)
    cards = award(model, fb)
    if cards:
        model["cats"] = list(model.get("cats") or []) + cards
        s.cards = s.cards + cards
        for c in cards:
            effects.append({"type": "card", "card": c})
    s.model = model
    s.feedback = None
    s.item = None
    effects.append({"type": "persist_feedback", "feedback": fb})
    return (s, effects)
def fold(events: list[Event]) -> State:
    s = State()
    for ev in events:
        s, _ = reduce(s, ev)
    return s
def _clone(x: dict) -> dict:
    import copy
    return copy.deepcopy(x)

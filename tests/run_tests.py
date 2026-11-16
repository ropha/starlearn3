"""零依赖测试：python tests/run_tests.py"""

import json
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core  # noqa: E402

BANK = json.loads((ROOT / "bank.json").read_text(encoding="utf-8"))
TEXT = next(i for i in BANK if i["题型"] == "text")
PIC = next(i for i in BANK if i["题型"] == "picture")
DRILL = next(i for i in BANK if i["题型"] == "drill")

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def run(events):
    s = core.State()
    for ev in events:
        s, _ = core.reduce(s, ev)
    return s


@test
def judge_text_and_picture():
    for item in (TEXT, PIC):
        assert core.judge(item, item["答案"])
        assert not core.judge(item, (item["答案"] + 1) % 4)
    assert not core.judge(TEXT, None)


@test
def judge_drill_rows():
    rows = core.expected_rows(DRILL)
    assert core.judge_drill(DRILL, rows)
    bad = list(rows)
    bad[0] = not bad[0]
    assert not core.judge_drill(DRILL, bad)
    assert not core.judge_drill(DRILL, rows[:-1])


@test
def drill_rechoose_then_advance_then_finish():
    """原版 drill：答错只闪可重选；答对才 subDone 并推进；全对才作答结束。"""
    s = run([
        {"type": "start", "at": 1000},
        {"type": "items_received", "at": 1001, "items": [DRILL]},
        {"type": "drill_row_shown", "at": 1100, "subIndex": 0},
    ])
    assert s.phase == "answering" and s.item["题型"] == "drill"
    rows = core.expected_rows(DRILL)
    s, fx = core.reduce(s, {"type": "drill_judge", "at": 2000, "subIndex": 0, "成立判断": not rows[0]})
    assert any(e["type"] == "neutral_rechoose" and e.get("drill") for e in fx)
    assert s.feedback["_meta"]["drillIndex"] == 0
    assert s.feedback["_meta"]["subDone"][0] is False
    assert s.feedback["_meta"]["subRows"][0]["重选次数"] == 0
    s, fx = core.reduce(s, {"type": "drill_judge", "at": 2100, "subIndex": 0, "成立判断": rows[0]})
    assert s.feedback["_meta"]["drillIndex"] == 1
    assert s.feedback["_meta"]["subDone"][0] is True
    assert s.feedback["_meta"]["subRows"][0]["重选次数"] == 1
    assert any(e["type"] == "show_item" and e.get("drillIndex") == 1 for e in fx)
    for r in range(1, len(rows)):
        s, fx = core.reduce(s, {"type": "drill_judge", "at": 2200 + r * 100, "subIndex": r, "成立判断": rows[r]})
    assert s.feedback["_meta"]["作答结束"] is True
    assert s.feedback["用户数据"]["首答对错"] is False
    assert any(e["type"] == "show_correct" for e in fx)


@test
def segments_explicit_and_auto():
    item = next(i for i in BANK if i.get("题干分段"))
    assert core.stem_segments(item) == tuple(item["题干分段"])
    auto = {"题干": "妈妈去超市买水果。妈妈买了 2 个苹果，爸爸又买回 3 个苹果。他们一共买了几个苹果？"}
    assert core.stem_segments(auto) == (
        "妈妈去超市买水果。",
        "妈妈买了 2 个苹果，爸爸又买回 3 个苹果。他们一共买了几个苹果？",
    )
    assert core.stem_segments({"题干": "只有一句话。"}) is None


@test
def pick_no_repeat_and_cycle():
    model = {"见过": [], "档": {"应用题": 1, "口算": 1}}
    picked = core.pick(BANK, model, 6, opening=True)
    assert len(picked) == 6
    assert len({i["id"] for i in picked}) == 6
    kps = [core.kp_of(i) for i in picked]
    assert kps.count("口算") >= 1


@test
def pick_exhausted_is_empty():
    model = {"见过": [i["id"] for i in BANK], "档": {"应用题": 1, "口算": 1}}
    assert core.pick(BANK, model, 6, opening=True) == []


@test
def flow_start_answer_next():
    s = run([
        {"type": "start", "at": 1000},
        {"type": "items_received", "at": 1001, "items": [TEXT, PIC]},
    ])
    assert s.phase == "answering" and s.item and s.item["id"] == TEXT["id"]
    assert s.answer_started_at == 1001
    s, effects = core.reduce(s, {"type": "option_pick", "at": 4001, "index": TEXT["答案"]})
    assert s.feedback["_meta"]["作答结束"]
    assert s.feedback["用户数据"]["首答对错"] is True
    assert s.feedback["用户数据"]["答题时长"] == 3.0
    assert any(e["type"] == "play_sfx" and e["name"] == "ok" for e in effects)
    s, _ = core.reduce(s, {"type": "next", "at": 4500})
    assert s.item and s.item["id"] == PIC["id"]
    assert len(s.pending) == 1


@test
def wrong_answer_flashes_and_retries():
    """原版：答错只发 neutral_rechoose，不结束本题，可重选；重选对才结束。"""
    s = run([
        {"type": "start", "at": 1000},
        {"type": "items_received", "at": 1001, "items": [TEXT]},
    ])
    wrong = (TEXT["答案"] + 1) % 4
    s, effects = core.reduce(s, {"type": "option_pick", "at": 3000, "index": wrong})
    assert s.feedback["用户数据"]["首答对错"] is False
    assert s.feedback["_meta"]["作答结束"] is False  # 没结束
    assert any(e["type"] == "neutral_rechoose" and e["index"] == wrong for e in effects)
    assert not any(e["type"] == "show_correct" for e in effects)
    s, effects = core.reduce(s, {"type": "option_pick", "at": 3500, "index": TEXT["答案"]})
    assert s.feedback["_meta"]["作答结束"] is True
    assert s.feedback["用户数据"]["重选次数"] == 1
    assert any(e["type"] == "play_sfx" and e["name"] == "ok" for e in effects)


@test
def undo_resets_and_counts():
    s = run([
        {"type": "start", "at": 1000},
        {"type": "items_received", "at": 1001, "items": [TEXT]},
    ])
    wrong = (TEXT["答案"] + 1) % 4
    s, _ = core.reduce(s, {"type": "option_pick", "at": 3000, "index": wrong})
    assert s.feedback["用户数据"]["首答对错"] is False
    s, effects = core.reduce(s, {"type": "undo_wrong", "at": 3500})
    assert s.feedback["用户数据"]["首答对错"] is None
    assert s.feedback["用户数据"]["重选次数"] == 1
    assert s.feedback["_meta"]["作答结束"] is False
    assert any(e["type"] == "show_item" for e in effects)


@test
def skip_goes_next_and_timeout_is_noop():
    s = run([
        {"type": "start", "at": 1000},
        {"type": "items_received", "at": 1001, "items": [TEXT, PIC]},
    ])
    s, _ = core.reduce(s, {"type": "skip", "at": 2000, "reason": "题目有问题"})
    assert s.phase == "answering"
    assert s.item["id"] == PIC["id"]
    assert len(s.pending) == 1
    assert s.pending[0]["用户数据"]["跳过原因"] == "题目有问题"
    before = s.feedback
    s, effects = core.reduce(s, {"type": "auto_submit_20s", "at": 30000})
    assert s.feedback == before and effects == []


@test
def fold_matches_replay():
    events = [
        {"type": "start", "at": 1000},
        {"type": "items_received", "at": 1001, "items": [TEXT]},
        {"type": "option_pick", "at": 4001, "index": TEXT["答案"]},
        {"type": "next", "at": 4500},
    ]
    s = core.fold(events)
    assert s.phase == "waiting"
    assert s.today_total == 1
    assert s.today_score == 1


@test
def absorb_and_fast_rise():
    model = {"见过": [], "档": {"应用题": 1}, "样本": {}}
    fb = core.new_feedback({"id": "x", "题型": "text", "主题": "应用题", "难度分数": 1, "预测答题时长": 10}, 1000)
    fb["用户数据"].update({"首答对错": True, "答题时长": 2.0})
    fb["_meta"]["作答结束"] = True
    fb["时间戳"]["作答"] = 3000
    model = core.absorb(model, fb)
    model = core.absorb(model, {**fb, "时间戳": {"出示": 1000, "作答": 4000, "反馈落定": None}})
    assert "x" in model["见过"]
    assert core.fast_rise(model, fb) == "应用题"
    model = core.set_tier(model, "应用题", 2)
    assert core.tier_of(model, "应用题") == 2


@test
def validate_ai_rejects_garbage():
    decision = {"items": ["nope"], "档位": {"应用题": 9}, "预测时长": {"nope": 1}}
    clean, errors = core.validate_ai(decision, BANK)
    assert clean["items"] == []
    assert any(e.startswith("unknown_item") for e in errors)
    assert any(e.startswith("bad_tier") for e in errors)



@test
def sim_rule_and_faults():
    import ai_sim
    sim = ai_sim.SimAI(BANK, mode="rule")
    d = sim.decide({"model": {"见过": [], "档": {"应用题": 1, "口算": 1}}, "items": BANK, "n": 6, "opening": True})
    clean, errors = sim.check(d)
    assert len(clean["items"]) == 6 and not errors
    bad = ai_sim.SimAI(BANK, mode="rule", faults={"bad_id", "bad_tier"})
    d = bad.decide({"model": {}, "items": BANK, "n": 6})
    _, errors = bad.check(d)
    assert any(e.startswith("unknown_item") for e in errors)
    assert any(e.startswith("bad_tier") for e in errors)
    empty = ai_sim.SimAI(BANK, mode="script", script=[{"items": [], "预测时长": {}, "档位": {}, "发卡": [], "理由": "x"}])
    assert empty.decide({})["items"] == []


@test
def third_clean_sample_awards_once():
    items = [i for i in BANK if i["题型"] == "text" and i["知识格"] == "kp-addsub-5" and i["难度分数"] == 1][:4]
    s = core.State()
    s, _ = core.reduce(s, {"type": "start", "at": 0})
    s, _ = core.reduce(s, {"type": "items_received", "at": 1, "items": items})
    cards = []
    for k in range(4):
        cur = s.item
        s, _ = core.reduce(s, {"type": "option_pick", "at": 2000 + k * 1000, "index": cur["答案"]})
        s, ef = core.reduce(s, {"type": "next", "at": 2500 + k * 1000})
        cards += [e for e in ef if e["type"] == "card"]
    assert len(s.cards) == 1, s.cards
    assert len(cards) == 1
    assert s.cards[0]["tier"] == "初识"


@test
def db_roundtrip_snapshot_and_restore():
    import os
    import tempfile
    import db as dbm

    path = os.path.join(tempfile.mkdtemp(), "app.sqlite")
    d = dbm.Db(path)
    user = "星月"
    s = core.State(user=user)

    def push(ev):
        nonlocal s
        d.append(user, ev)
        s, _ = core.reduce(s, ev)
        d.maybe_snapshot(user, s)

    push({"type": "start", "at": 1000})
    push({"type": "items_received", "at": 1001, "items": [i for i in BANK if i["题型"] != "drill"][:10]})
    for k in range(9):
        cur = s.item
        push({"type": "option_pick", "at": 2000 + k * 100, "index": cur["答案"]})
        push({"type": "next", "at": 2050 + k * 100})

    r = d.restore(user)
    assert r.phase == s.phase
    assert r.today_total == s.today_total == 9
    assert len(r.pending) == len(s.pending)
    assert [i["id"] for i in r.pool] == [i["id"] for i in s.pool]
    assert r.model.get("见过") == s.model.get("见过")
    assert d.count(user) >= 20
    assert d.con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] >= 1

    d.add_cards(user, [{"node": "kp-addsub-5", "tier": "初识", "at": 1, "source": "rule"}])
    d.add_cards(user, [{"node": "kp-addsub-5", "tier": "初识", "at": 2, "source": "rule"}])
    assert len(d.cards(user)) == 1

    d.save_model(user, {"见过": ["a"], "档": {"应用题": 2}})
    assert d.load_model(user)["档"]["应用题"] == 2
    d.log_ai(user, 1, {"items": []}, True, 12, context={"n": 1})
    d.close()

if __name__ == "__main__":
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print("ok   ", fn.__name__)
        except Exception:
            failed += 1
            print("FAIL ", fn.__name__)
            traceback.print_exc()
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)

from __future__ import annotations
import json
import pathlib
import time
from typing import Any
import core
ROOT = pathlib.Path(__file__).resolve().parent
FAULTS = ("timeout", "bad_id", "bad_tier", "empty", "partial")
class SimAI:
    def __init__(
        self,
        bank: list[dict],
        mode: str = "rule",
        script: list[dict] | None = None,
        recording: list[dict] | None = None,
        faults: set[str] | None = None,
    ):
        if mode not in ("rule", "script", "replay", "record"):
            raise ValueError(f"unknown mode {mode}")
        self.bank = bank
        self.mode = mode
        self.script = script or []
        self.recording = recording or []
        self.faults = faults or set()
        self.step = 0
        self.calls: list[dict] = []
        for f in self.faults:
            if f not in FAULTS:
                raise ValueError(f"unknown fault {f}")
    def decide(self, ctx: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"ctx": _slim(ctx), "at": time.time()})
        if "timeout" in self.faults:
            time.sleep(5)
            raise TimeoutError("sim timeout")
        decision = self._base(ctx)
        if self.mode == "script":
            decision = self._from_script()
        elif self.mode == "replay":
            decision = self._from_recording()
        self.step += 1
        if "empty" in self.faults:
            decision["items"] = []
        if "bad_id" in self.faults:
            decision["items"] = list(decision.get("items") or []) + ["not-a-real-id"]
        if "bad_tier" in self.faults:
            decision["档位"] = {"应用题": 9, "口算": 0}
        if "partial" in self.faults:
            ids = list(decision.get("items") or [])
            decision["预测时长"] = {ids[0]: 12} if ids else {}
        return decision
    def _base(self, ctx: dict) -> dict:
        model = ctx.get("model") or {}
        items = ctx.get("items") or self.bank
        n = int(ctx.get("n") or 6)
        picked = core.pick(items, model, n, opening=bool(ctx.get("opening")))
        return {
            "items": [i["id"] for i in picked],
            "预测时长": {i["id"]: i.get("预测答题时长") or 12 for i in picked},
            "档位": {"应用题": core.tier_of(model, "应用题"), "口算": core.tier_of(model, "口算")},
            "发卡": [],
            "理由": f"sim:{self.mode}",
        }
    def _from_script(self) -> dict:
        if not self.script:
            return {"items": [], "预测时长": {}, "档位": {}, "发卡": [], "理由": "script:empty"}
        return dict(self.script[min(self.step, len(self.script) - 1)])
    def _from_recording(self) -> dict:
        if not self.recording:
            return {"items": [], "预测时长": {}, "档位": {}, "发卡": [], "理由": "replay:empty"}
        return dict(self.recording[min(self.step, len(self.recording) - 1)])
    def check(self, decision: dict) -> tuple[dict, list[str]]:
        return core.validate_ai(decision, self.bank)
def load_script(name: str) -> list[dict]:
    return json.loads((ROOT / "tests" / "scripts" / name).read_text(encoding="utf-8"))
def load_recording(name: str) -> list[dict]:
    return json.loads((ROOT / "tests" / "recordings" / name).read_text(encoding="utf-8"))
def _slim(ctx: dict) -> dict:
    return {
        "user": ctx.get("user"),
        "opening": ctx.get("opening"),
        "n": ctx.get("n"),
        "seen": len((ctx.get("model") or {}).get("见过") or []),
    }

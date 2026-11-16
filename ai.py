from __future__ import annotations
import json
import os
import re
import time
import urllib.request
from typing import Any
import ai_sim
import core
MODE = os.environ.get("XINGYUE_AI", "sim").strip().lower()
class Brain:
    def __init__(self, bank: list[dict], db=None, sim_mode: str = "rule"):
        self.bank = bank
        self.db = db
        self.sim = ai_sim.SimAI(bank, mode=sim_mode)
    def decide(self, ctx: dict[str, Any]) -> tuple[dict, bool, str]:
        t0 = time.monotonic()
        try:
            raw = self._real(ctx) if MODE == "real" else self.sim.decide(ctx)
            clean, errors = core.validate_ai(raw, self.bank)
            if errors:
                raise ValueError(",".join(errors))
            if not clean["items"]:
                raise ValueError("empty_items")
            ok, err = True, ""
        except Exception as exc:
            clean, err = self._fallback(ctx), str(exc)
            ok = False
        latency = int((time.monotonic() - t0) * 1000)
        if self.db is not None:
            try:
                self.db.log_ai(ctx.get("user", "?"), int(time.time() * 1000), clean, ok, latency, err, ctx)
            except Exception:
                pass
        return clean, ok, err
    def _fallback(self, ctx: dict) -> dict:
        items = ctx.get("items") or self.bank
        model = ctx.get("model") or {}
        picked = core.pick(items, model, int(ctx.get("n") or 6), opening=bool(ctx.get("opening")))
        return {
            "items": [i["id"] for i in picked],
            "预测时长": {i["id"]: i.get("预测答题时长") or 12 for i in picked},
            "档位": {"应用题": core.tier_of(model, "应用题"), "口算": core.tier_of(model, "口算")},
            "发卡": [],
            "理由": "fallback:rule",
        }
    def _real(self, ctx: dict) -> dict:
        url = os.environ.get("XINGYUE_AI_URL", "").strip()
        if not url:
            raise RuntimeError("XINGYUE_AI_URL 未配置")
        key = os.environ.get("XINGYUE_AI_KEY", "").strip()
        seen = set((ctx.get("model") or {}).get("见过") or [])
        payload = {
            "题目池": [
                {
                    "id": i["id"],
                    "题型": i.get("题型"),
                    "主题": i.get("主题"),
                    "难度分数": i.get("难度分数"),
                    "知识点": i.get("知识点") or i.get("知识格"),
                    "见过": i["id"] in seen,
                }
                for i in (ctx.get("items") or self.bank)
            ],
            "模型": ctx.get("model") or {},
            "本次需要": int(ctx.get("n") or 6),
            "输出字段": core.AI_SCHEMA,
        }
        body = json.dumps(
            {
                "model": os.environ.get("XINGYUE_AI_MODEL", "deepseek-chat"),
                "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                "temperature": 0.2,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get("XINGYUE_AI_TIMEOUT", "30"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{[\s\S]*\}", str(text))
        if not m:
            raise ValueError("AI 未返回 JSON")
        return json.loads(m.group(0))

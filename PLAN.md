# starLearn 3 规划

纯 Python 单进程学习机。没有服务端、没有浏览器、没有双库。对外只有两个请求：AI 和豆包朗读。

## 1. 目标

- 出一道适合星月的题 → 读题 → 判对错 → 记表现 → 决定下一题 → 发猫卡 → 结束。
- 教学判断（选题、难度、预测、掌握度、发卡）全部交给 AI；程序只做数据、校验、兜底、记账。
- 代码量从现有 11,500 行压到 **~2,400 行**，其中 `core.py` 一个文件装全部教学逻辑。

## 2. 非目标

- 不做多设备同步（不需要 iPad）。
- 不做云端账号、部署、隧道、nginx。
- 不做质量门报表、日报、决策回放（旧 `jobs/` 全部删除）。
- 不做多路 TTS 回退（豆包失败 → 系统语音 → 静音）。

## 3. 形态

```
starlearn3.exe（PySide6 单进程）
  ├─ core.py     教学逻辑全部（纯函数，无 Qt / 无 IO）
  ├─ main.py     启动、窗口、页面路由、串口
  ├─ db.py       sqlite3：事件 / 模型 / 猫卡 / AI 日志
  ├─ ai.py       LLM 调用 + 校验 + 降级
  ├─ ai_sim.py   AI 模拟器（全真模拟生题）
  ├─ tts.py      豆包 + wav 缓存 + 播放
  ├─ audio.py    音效
  ├─ keypad.py   QSerialPort 读 ESP32 键盘
  ├─ theme.py    颜色、字体、QSS
  ├─ pages/
  │   ├─ home.py     首页：选用户、开始
  │   ├─ quiz.py     答题页：题干两段、选项、计时、家长键
  │   ├─ gallery.py  结束页：猫卡画廊
  │   └─ widgets.py  猫卡发光、选项按钮、分段题干
  ├─ bank.json   题库（数据，不计代码）
  └─ assets/     猫图、音效
```

## 4. core.py 边界

读 `core.py` 一个文件，应该能回答所有“系统怎么想”：

1. 数据模型：`Item / State / Event / Effect / Feedback`
2. 常量：20 秒自动提交、答题时限、档位 1–3、5 应用题 + 1 口算周期
3. 判分：text/picture 单选、drill 五个算式逐行
4. 分段：显式 `题干分段` 优先，否则按第一个数字句切
5. 选题：去重、档位匹配、没题就停、题库筛选
6. 掌握度：样本、档位、四档猫卡（AI 优先，规则兜底）
7. 预测：接口约定 + 记录实际用时与误差
8. 事件 fold：从事件重放状态
9. AI 接口：输入包、输出 schema、校验、降级
10. 猫卡：初识→在练→熟练→进阶，不重发、不收回

**不放进 core**：SQLite、Qt、HTTP、TTS、串口。core 只定义接口，由 `db / pages / tts / keypad` 实现。

## 5. 数据

一个 `data/app.sqlite`：

| 表 | 内容 |
|---|---|
| `events` | append-only，`id / user / at / kind / payload` |
| `models` | 每用户一条：见过、样本、档位、猫卡判定 |
| `cats` | 每用户每档一条：node / tier / at / source |
| `ai_logs` | 决策输入摘要、输出、置信、耗时、实际用时、误差 |
| `snapshots` | 每 20 条事件一个快照，启动增量恢复 |

`bank.json` 直接读进内存，不建表。

## 6. AI 接口

```python
decide(input: dict) -> dict
# 输出：{"items": [id...], "预测时长": {id: 秒}, "档位": {"应用题": 1-3, "口算": 1-3}, "发卡": [{"node","tier"}], "理由": str}
```

输入包（程序组装，不进 core 的 IO）：
- 最近 20 题：id、难度、用时、对错、重选、重听、家长标签
- 按知识点×难度的中位数/趋势
- 题库候选：id、知识点、难度、先验时长、是否见过
- 上次预测 vs 实际

校验三条：题 id 存在、档位在 1–3、预测时长在 3–60 秒。任一不合法 → 降级到规则兜底。

## 7. AI 模拟器（ai_sim.py）

目标：**不烧 token 也能全真跑通**，同时能测降级。

四种模式：

| 模式 | 行为 |
|---|---|
| `script` | 按 `tests/scripts/*.json` 逐题返回，端到端可复现 |
| `rule` | 用 core 的最小规则模拟（按档位选没见过的题、预测=先验） |
| `replay` | 回放录制的真实 AI 响应（`record` 产物） |
| `record` | 包一层真实 `ai.py`，把请求/响应写进 `tests/recordings/*.json` |

故障注入（用于验证降级，不崩课堂）：
- `timeout`：延迟 5 秒后抛超时
- `bad_id`：返回不存在的题 id
- `bad_tier`：档位返回 0 或 9
- `empty`：返回空列表
- `partial`：返回 3 题但只给 1 题的预测时长

模拟器与真实 AI 共用同一份输出 schema 和校验，所以“模拟器能跑通”= “真实 AI 的格式也没问题”。

## 8. 对外请求

| 请求 | 从哪发 | 去哪 |
|---|---|---|
| AI 决策 | `ai.py` | LLM HTTP API |
| 豆包朗读 | `tts.py` | 豆包 TTS |

没有 `/出题`、`/事件`、`/掌握度快照`。键盘是本地串口，不算对外。

## 9. 从旧系统删什么

| 删除 | 行数 |
|---|---|
| `apps/server` 全部（app/db/tts/mastery/analyst/jobs/seed/warehouse/idempotency/parse） | ~7,100 |
| `packages/schema`（zod） | 385 |
| `client` 的 IndexedDB / 双库 / probe / 多路 TTS / WebSocket 键盘桥 | ~1,900 |
| 旧 `packages/core` 的 TS 版（逻辑迁到 core.py） | 980 |

保留并迁移：`bank.json`（题库）、猫图、音效、豆包 key、ESP32 串口协议。

## 10. 里程碑

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 | `core.py` + `bank.json` + pytest 20 题 | 状态机、判分、分段、选题、fold 全绿 |
| M2 | `db.py` + 快照 | 重启 50ms 内恢复，事件不丢 |
| M3 | `pages/home.py` + `pages/quiz.py`，最小闭环 | 能答完 5 题，键盘可选 |
| M4 | `tts.py` + `ai.py` + `ai_sim.py` | 模拟器能跑通一整节；真实 AI 可切换 |
| M5 | 动画、画廊、音效、家长键 | 猫卡发光、选项弹跳、结束页 |
| M6 | Nuitka 打包 | 双击 exe 能上课 |

## 11. 验收

- 断网（除 AI/TTS）能跑完一节课。
- AI 模拟器四种模式都跑通，五种故障都能降级。
- `core.py` 单文件 ≤ 1,200 行，读一遍能讲清全部教学规则。
- 全部代码 ≤ 2,600 行（不含 `bank.json` 和 assets）。
- 启动到首页 ≤ 1.5 秒。

## 12. 风险

| 风险 | 处理 |
|---|---|
| Qt 富文本不支持透明度 | 暗段用颜色 + 字号模拟，不做渐隐 |
| SVG 复杂图形掉细节 | 现有题库是简单形状，先验证 `QSvgWidget` |
| AI 直连 CORS / key 暴露 | `ai.py` 走本地进程直连，key 只在本地配置 |
| 清缓存/换机丢数据 | SQLite 文件即数据，复制即备份 |
| 单文件过大难维护 | 严格边界：core 不碰 IO；超过 1,200 行就拆出 `rules.py` |

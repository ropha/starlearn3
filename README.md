# starLearn 3

纯 Python 单进程学习机。完整规划见 [PLAN.md](PLAN.md)。

## 跑

```bash
python tests/run_tests.py
```

零依赖，不需要 pytest。

## 当前进度

| 阶段 | 状态 |
|---|---|
| M1 `core.py` + `bank.json` + 测试 | 完成（13/13） |
| M2 `db.py` + 快照 | 完成（14/14） |
| M3 首页 + 答题页 | 完成 |
| M4 `tts.py` + `ai.py` + 真实 AI 切换 | 未开始 |
| M5 动画 / 画廊 / 家长键 | 未开始 |
| M6 Nuitka 打包 | 未开始 |

## 文件

| 文件 | 说明 |
|---|---|
| `core.py` | 教学逻辑全部：判分、分段、选题、掌握度、reducer、fold |
| `db.py` | SQLite：事件 / 模型 / 猫卡 / AI 日志 / 快照 |
| `ai_sim.py` | AI 模拟器：rule / script / replay / record + 五种故障注入 |
| `bank.json` | 题库 104 题（数据） |
| `tests/run_tests.py` | 零依赖测试 |

## 约束

- `core.py` 不碰 Qt / SQLite / HTTP / TTS / 串口，只返回 Effect。
- 时间只从事件里的 `at` 来。
- 对外只有 AI 和豆包朗读。

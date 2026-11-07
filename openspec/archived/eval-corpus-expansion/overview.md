# Change Overview：评测语料扩集 + 回归加固（Eval Corpus Expansion）

> 扩充 `eval/cases/` 三文件（召回 / 关联 / 边界 / 安全注入），让 schema 检索、意图路由、SQL 校验的回归覆盖更密，防退化。

## Why（为什么做）

`eval/cases/` 用例仍偏少：`schema_linking` 只有 6 例、`route_guard` 12 例、`security_deny` 6 例（Backlog TASK-BACKLOG-003）。召回/关联/安全边界覆盖不足，一次改动可能带跑一个没测到的维度。

## What（做什么 / 不动什么）

- **修改** `eval/cases/schema_linking.json`：补多表关联召回、列注释驱动召回、计数/聚合召回。
- **修改** `eval/cases/routing_guard.json`：补更多图表词（折线/饼图/占比）、结构询问、清空类恶意、加合法控制组。
- **修改** `eval/cases/security_deny.json`：补恒真/恒假字面比较注入拒绝 + 合法 `列='值'` 过滤放行控制组（与本轮注入加固 change 配套）。
- **不动**：`run_eval.py` 判定逻辑、`build_test_index`、scenario 定义（保持确定性）。
- **测试**：跑 `eval/run_eval.py` 保持「该拒必拒 / 误放行=0 / 召回全命中」。

## How（怎么落地，一句概览）

在三个 JSON 里追加用例（只加不变判），跑 `run_eval.py` 逐条核对，任一新增 FAIL 就修 expected 到确定性真值。

---

- 关联模块：`eval/cases/*.json` · `eval/run_eval.py`
- 关联 CAP：CAP-EVAL-001/002/003 · TASK-BACKLOG-003
- 涉及测试：`eval/cases/`（扩充）· `py -m eval.run_eval`
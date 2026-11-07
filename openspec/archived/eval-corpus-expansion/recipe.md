# Change Recipe：评测语料扩集 + 回归加固（执行剧本）

> 给 LLM 的逐步执行清单。

## Step 1 —— 读约定 + 确认「只加语料」
- **Context**: 语料是确定性的；改动判定逻辑会带不确定性与回归风险。
- **Action**: 读 `openspec/agreement.md`；确认本轮**只增 `eval/cases/*.json` 用例，不改 `run_eval.py` 判定**。
- **Validation**: 已确认为纯语料扩充。 `[ ]`

## Step 2 —— 扩 `schema_linking.json`
- **Action**: 追加 proposal 中的 s07–s11（多表关联/列名/列注释驱动召回）。
- **Validation**: `py -m eval.run_eval` 中 schema_linking 类新用例全 PASS（部分命中 top-3）。 `[ ]`

## Step 3 —— 扩 `routing_guard.json`
- **Action**: 追加 r13–r17（图表词/结构/清空恶意/合法聚合控制）。
- **Validation**: `run_eval` 中 routing_guard 新用例全 PASS（与 `_routing_deny_expect` 一致）。 `[ ]`

## Step 4 —— 扩 `security_deny.json`
- **Action**: 追加拒 4 + 控制 2（恒真/恒假/sleep + 合法 `列='值'`/常量过滤控制）。**需先合入注入加固 change 的 validator 才拒得动**；控制组必须放行（锁死不误杀）。
- **Validation**: `run_eval` 中 security_deny 新用例全 PASS，「误放行=0」。 `[ ]`

## Step 5 —— 全量校验
- **Action**: `py -m eval.run_eval`（全部 PASS）→ `py -m pytest tests/ -q`。
- **Validation**: 两条命令全绿。任何新用例 FAIL 只允许调整该例 `expected*` 至确定性真值。 `[ ]`

## Final —— 收尾
- `CHANGELOG.md` 记语料扩集与用例数变化；本 change 目录移 `openspec/archived/`；中文主题提交。 `[ ]`
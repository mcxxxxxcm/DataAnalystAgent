# Change Recipe：确定性回归评测(坏case/错误案例/评测集)

> 给 LLM 的逐步执行清单。每步 = Context(为什么) + Action(做什么) + Validation(怎么验证通过)。
> 执行后逐条打 `[x]`。

## Step 1 —— 读约定 / 确认分层
- **Context**: 动手前对齐宪法,避免越层、触碰安全红线。
- **Action**: 重读 `openspec/agreement.md`。确认:新增 intent_guard 属 **core 层**(不暴露给 LLM、纯逻辑);评测属 **eval 层**;本轮不接 tools/agent/api 运行时。
- **Validation**: 在 `proposal.md`「分层归属」已写明 core 层 + eval 层,不触碰 §3 安全红线(不放开写操作、不取消 HITL、新增工具仍 read-only)。 `[x]`

## Step 2 —— 新增 intent_guard.py
- **Context**: 错误路由(拒答/澄清/报错)要确定性断言,现有代码无此入口,先补纯逻辑路由器。
- **Action**:
  1. 建 `core/security/intent_guard.py`,定义 `Intent` 枚举 + `IntentVerdict` dataclass(`category/deny/clarify/reason`)。
  2. 实现 `classify_intent(text, table_index)`:恶意信号正则 → 寒暄正则 → 复用 `core/database/schema_linking.py` 的 `rank_relevant_tables` 判实体,细分 CHART/INFO/QUERY;无实体→ OUT_OF_SCOPE 或 AMBIGUOUS。所有命中保守(低误杀)。
  3. tokenizer 复用 `schema_linking` 的 `_STOP_CHARS`/`_tokenize`,不新造。
- **Validation**: 手写快速调用几个样例,`MALICIOUS/SMALLTALK/AMBIGUOUS/QUERY` 分类符合预期;合法查询 `deny=False`。 `[x]`

## Step 3 —— 重建评测集(cases/)
- **Context**: 现有 5 条 golden 太薄,`sql_contains` 是死字段;要按三类场景结构化、并入坏 case 种子。
- **Action**:
  1. 建 `eval/cases/schema_linking.json`(s01-s05)、`security_deny.json`(sec01-05 + accept01)、`routing_guard.json`(r01-r08),字段含 `id/nl/expected/source/note`。
  2. 用 `eval/run_eval.py` 的合成索引(TableIndex.add sales/users/orders/products)对齐种子。
  3. 删旧 `eval/golden_queries.json`;写 `eval/badcases.md` 台账;写 `eval/mine_badcases.py`(扫 tool_calls.jsonl dump 失败用例)。
- **Validation**: 三类 JSON 可被 json.load,字段齐;合成索引列名与种子 nl 对齐(Avoid§1:不硬编码示例表进提示词,但评测种子用真实合成索引是允许的)。 `[x]`

## Step 4 —— 重写 run_eval.py
- **Context**: harness 要从"单场景 5 条"扩成"三类聚合 + 硬门槛 + 失败非零退出"。
- **Action**:
  1. 按 `scenario` 分发:`schema_linking` 断言 `rank_relevant_tables` precision@K;`security_deny` 断言 `SQLValidator(enable_write=False).validate(sql).is_valid==False`(accept01 反向断言放行);`routing_guard` 断言 `classify_intent` 的 verdict 匹配(expected deny 必 deny、expected clarify 必 clarify)。
  2. 输出每例 PASS/FAIL + 汇总指标(表检索 precision、安全/路由误放行=0),任一 FAIL `return 1`。
  3. 兼容 `py -m eval.run_eval` 入口。
- **Validation**: 跑 `py -m eval.run_eval`,三类种子全过或"行为应然"判据下合理;误放行(该拒的放了)显式 FAIL。 `[x]`

## Step 5 —— 阈值进 config
- **Context**: 约定"配置进 settings 并给默认值、不硬编码"。
- **Action**: `config/settings.py` 加路由/恶意词/注入开关默认值(本轮默认供 harness,不改变既有行为)。
- **Validation**: 读配置能取到默认值;run_eval 不因配置缺失报错。 `[x]`

## Step 6 —— 测试
- **Context**: 测试是硬门槛。
- **Action**:
  1. 新增 `tests/test_intent_guard.py`:各分类合法/非法样例 + 巡逻防误杀(合法查询不 deny)。
  2. 新增 `tests/test_eval_regression.py`:完整 harness `fail==0` + 该拒必拒硬门槛断言。
  3. 更新 `tests/test_eval_text2sql.py`:改用新 cases 加载器(不再引用已删的 golden_queries.json,Avoid§3)。
- **Validation**: `pytest tests/ -q` 全绿。 `[x]`

## Step 7 —— 用户可见/记录性变更
- **Context**: 约定用户可见变更更新 README、记录性变更追加 CHANGELOG。
- **Action**: `README.md` 补"回归评测怎么跑/坏 case 归置";`CHANGELOG.md` 追加本改动。
- **Validation**: 文档与实际命令(如 `py -m eval.run_eval`、`pytest tests/ -q`)一致。 `[x]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How 逐条核对:新增 intent_guard ✓、cases/ 三类 ✓、harness 聚合+硬门槛 ✓、死字段已删 ✓、本轮不接线 ✓。
- change 目录移出 `changes/`(归档或删除)。
- 提交信息中文一句主题,如 `git commit -m "确定性回归评测(进CI):新增意图路由+三类评测集"`,附 Co-Authored-By。 `[x]`
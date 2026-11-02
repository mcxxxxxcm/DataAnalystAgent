# Change Proposal：意图路由器接线 `/query`

## 方案

**现状** → **目标** → **改动清单**

**现状**：`core/security/intent_guard.py` 的 `classify_intent(text, table_index, ...)` 是纯函数，把 NL 分类成 QUERY/CHART/INFO/MALICIOUS/SMALLTALK/OUT_OF_SCOPE/AMBIGUOUS 并带 `deny`/`clarify` 布尔。目前仅 `eval/run_eval.py` 直调，`/query` 运行时未接线；`settings.enable_intent_router` 默认 `False`。

**目标**：`ENABLE_INTENT_ROUTER=True` 时，`/query` 先把用户请求过意图门——命中明确「恶意 / 寒暄 / 离题」直接短片返回文案，**不进 LLM**；其余（含歧义）照常进 Agent。默认关 → 零行为变化。

**改动清单**：

- 修改：`core/security/intent_guard.py` —— 新增 `maybe_short_circuit(text) -> Optional[str]` 纯函数：
  - `settings.enable_intent_router` 为 False → 返回 `None`。
  - `classify_intent(...)` 结果 `verdict.deny` 为 True（MALICIOUS / SMALLTALK / OUT_OF_SCOPE）→ 返回 `verdict.reply or verdict.reason` 文案。
  - 非 deny（含 AMBIGUOUS / QUERY / CHART / INFO）→ 返回 `None`（**不短路 clarify**，避免误拒合法查询）。
  - `table_index`：调用方注入。真路由用全局 `schema_manager` 的惰性 `_get_index()`（`core/database/schema.py`）；构建失败/无表时回退空 `TableIndex()`——纯正则类 deny 不依赖实体命中仍可短路。
- 修改：`api/routes.py` —— `/query`（`query()`）在 `get_async_agent()` 之前插入：
  ```python
  reject_reply = await maybe_short_circuit(request.query)
  if reject_reply:
      return QueryResponse(success=False, thread_id=thread_id, message=reject_reply)
  ```
- 修改（读不改）：`config/settings.py` —— 仅确认 `enable_intent_router` 存在，默认 `False`。
- 不新增配置、不新增工具、不改 `classify_intent` 本体与 schema linking 语义。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 短路策略 | 只短路 `deny`，不短路 `clarify` | 对齐 intent_guard「保守、低误杀」；歧义交 LLM 更稳 | 歧义流量仍进 LLM（non-goal） |
| 实体判定是否需要实时索引 | 用 `schema_manager._get_index()`，失败回退空索引 | 复用既有一致索引，避免另造一套（Avoid#4） | 首次构建索引会触一次 DB（仅开启开关时才有该路径） |
| 接入点 | `/query` 入口、Agent 调用前 | 最前置，最短路径省 LLM | 只覆盖 `/query`，不覆盖 `/stream` / `/approve` |

## 兼容性

- **向后兼容**：`enable_intent_router` 默认 `False` → 现有行为、API 响应、前端字段完全不变。
- **开关打开后**：命中 `MALICIOUS/SMALLTALK/OUT_OF_SCOPE` 时 `/query` 返回 `success=False` + 文案，`thread_id` 照常生成、无 `data/chart`。属预期新行为，不影响既有合法查询路径。
- 不触碰 SQL 安全校验 / HITL / 图表 / 记忆任意一环。

## 测试计划

新增 `tests/test_intent_router_wiring.py`（纯逻辑，monkeypatch `settings` + `schema_manager`，不连 DB/LLM）：

1. `enable_intent_router=False` → 各种输入 `maybe_short_circuit` 均返回 `None`（零行为变化）。
2. 开启 + 恶意（`删除全部数据` / `drop table` / `绕过审批`）→ 返回非空文案。
3. 开启 + 寒暄（`你好`）→ 返回礼貌文案。
4. 开启 + 离题（`推荐一部电影`）→ 返回非空文案。
5. 开启 + 合法查询（`查询各地区销售额`，空索引）→ 返回 `None`（放行；空索引下非 deny 不误拒）。
6. 开启 + 歧义（`那个多少钱`，空索引）→ 返回 `None`（不短路 clarify，走 LLM）。

沿用 `tests/test_intent_guard.py` 的 monkeypatch 手法（`settings`、`schema_manager._get_index`）。既有 121 项 + 新用例 `pytest tests/ -q` 全绿为门槛。
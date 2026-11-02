# Change Recipe：意图路由器接线 `/query`（执行剧本）

> 给 LLM 的逐步执行清单。执行后对着每步 Validation 自检一遍，打 `[x]`。

## Step 1 —— 读约定
- **Context**：动手前先对齐项目宪法，确认分层与安全红线。
- **Action**：读 `openspec/agreement.md`。本 change 落在 `core/security/`（适配器）+ `api/`（接线）两层；不触碰安全红线（不放松任何校验，仅新增短路）；不造重复实检索（复用 `schema_manager._get_index`）。
- **Validation**：已在 `proposal.md` 写清分层与取舍。`[x]`

## Step 2 —— 加 `maybe_short_circuit` 纯函数
- **Context**：把 intent_guard 的 deny 判定封装成可注入、可单测的回函，供 `/query` 在进 LLM 前短路。
- **Action**：在 `core/security/intent_guard.py` 新增：
  ```python
  async def maybe_short_circuit(
      text: str,
      table_index=None,
      allow_smalltalk: bool = True,
  ) -> Optional[str]:
      """开启 ENABLE_INTENT_ROUTER 时，仅对明确 deny 意图返回短路文案；否则返回 None。
      不短路 clarify（歧义放行进 LLM），保守低误杀。table_index 可注入；缺省回退空索引。"""
      from config.settings import get_settings
      if not get_settings().enable_intent_router:
          return None
      try:
          idx = table_index
          if idx is None:
              from core.database import schema_manager
              idx = await schema_manager._get_index()
      except Exception:
          from core.database.schema_linking import TableIndex
          idx = TableIndex()
      verdict = classify_intent(text, idx, allow_smalltalk=allow_smalltalk)
      if verdict.deny:
          return verdict.reply or verdict.reason
      return None
  ```
  （`import` 放函数内避免顶层循环依赖；`classify_intent` 已定义于同文件顶部。）
- **Validation**：`python -c "from core.security.intent_guard import maybe_short_circuit"` 可导入。`[x]`

## Step 3 —— 接线 `/query`
- **Context**：在最短路径上短路，避免恶意/寒暄/离题请求进 LLM。
- **Action**：`api/routes.py` 的 `query()` 中，`thread_id` 生成之后、`agent = await get_async_agent()` 之前插入：
  ```python
  reject_reply = await maybe_short_circuit(request.query)
  if reject_reply:
      return QueryResponse(success=False, thread_id=thread_id, message=reject_reply)
  ```
  文件顶部 `from core.security.intent_guard import maybe_short_circuit`。
- **Validation**：`python -c "import api.routes"` 不报错；确认插入点在 Agent 调用之前。`[x]`

## Step 4 —— 新增测试
- **Context**：本仓库测试是硬门槛；此 change 需覆盖开关开/关与 deny/放行/歧义五态。
- **Action**：新增 `tests/test_intent_router_wiring.py`（monkeypatch `get_settings` 返回带 `enable_intent_router` 的对象、`schema_manager._get_index` 抛异常回退空索引），覆盖 proposal 测试计划 6 例。
- **Validation**：新用例全过，且覆盖开关关闭时恒 `None`。`[x]`

## Step 5 —— 回归
- **Context**：确认不破坏既有基线与评测。
- **Action**：`pytest tests/ -q`；`py -m eval.run_eval`。
- **Validation**：`pytest tests/ -q` 全绿（121 + 新增）；eval 不回归（routing_guard 仍 PASS）。`[x]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How 逐条核实（默认关零行为变化；only-deny 短路）。
- 更新 `README.md`（配置表/安全设计注明开启后前置拒答）、`openspec/specs/spec.md`（CAP-SEC-009 状态）、`openspec/tasks.md`（B004 [todo]→已落地）、`openspec/terminology.md`（TERM-014 补接线事实）、`CHANGELOG.md`。
- 本 change 目录移出 `changes/` → `archived/`。
- 提交用中文一句主题 + `Co-Authored-By`。`[x]`
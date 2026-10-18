# Change Recipe：修复瞬时错误重试链路 + schema 缓存 TTL（执行剧本）

> 给 LLM 的逐步执行清单。每步 Context / Action / Validation，执行后对 Validation 自检并打 `[x]`。

## Step 1 —— 读约定
- **Context**: 动手前对齐项目宪法，确认分层与安全红线。
- **Action**: 读 `openspec/agreement.md`；确认本 change 触及 middleware / tools / core 三层、不碰安全红线（不改 SQL 校验、不放宽写权限）、注意 Avoid#2（缓存有界）、Avoid#4（不重复实现）。
- **Validation**: 已在 `proposal.md` 标明层级与「移除重叠中间件」。 `[x]`

## Step 2 —— 移除坏的 ToolErrorMiddleware
- **Context**: `ToolErrorMiddleware()` 无参构造即抛 ValueError，导致 get_middleware_list/_create_agent 崩；且职责与重试/自纠重叠。
- **Action**: 编辑 `middleware/config.py`：删除 `middlewares.append(ToolErrorMiddleware())`；顶部 import 改为仅 `from langchain.agents.middleware import ToolRetryMiddleware`。
- **Validation**: `grep -n "ToolErrorMiddleware" middleware/config.py` 无结果；`get_middleware_list()` 不再抛异常且含 `ToolRetryMiddleware`。 `[ ]`

## Step 3 —— query_database 瞬时错误分流
- **Context**: 当前 `except Exception` 吞掉瞬时错误，重试中间件永不触发。
- **Action**: 编辑 `tools/sql_tools.py`：import 加 `is_transient_error`；`except Exception as e:` 内先 `if is_transient_error(e): raise`，再走原结构化失败返回。
- **Validation**: `grep -n "is_transient_error" tools/sql_tools.py` 命中；瞬时异常对象将向上抛出（未被转 success=false）。 `[ ]`

## Step 4 —— schema 缓存 TTL 修正
- **Context**: `timedelta.seconds` 跨天回绕，缓存超一天永久不刷新。
- **Action**: 编辑 `core/database/schema.py` 第 114 行，`.seconds` 改 `.total_seconds()`。
- **Validation**: `grep -n "total_seconds" core/database/schema.py` 命中 get_table_schema 缓存分支。 `[ ]`

## Step 5 —— 加测试
- **Context**: 本仓库硬门槛，改动必须带测试且不触真实库。
- **Action**: 新建 `tests/test_sql_tools.py`、`tests/test_schema_cache.py`；`tests/test_tool_boundaries.py` 追加中间件构建用例（均按 proposal「测试计划」）。
- **Validation**: `pytest tests/test_sql_tools.py tests/test_schema_cache.py tests/test_tool_boundaries.py -q` 通过。 `[ ]`

## Step 6 —— 全量测试
- **Context**: 全量是最终门槛。
- **Action**: 项目根跑 `pytest tests/ -q`。
- **Validation**: 全绿。 `[ ]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How 逐条核对兑现（移除中间件 / 瞬时分流 / total_seconds）。
- 无用户可见字段变化 → 不强改 README；记录性变更追加 `CHANGELOG.md`。
- 本 change 目录移出 `changes/`（归档或删除）。
- 提交用中文一句主题，附 `Co-Authored-By`。 `[ ]`
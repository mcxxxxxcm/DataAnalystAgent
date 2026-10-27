# Change Recipe：并发压测与并发能力提升（执行剧本）

> 给 LLM 的逐步执行清单。每步 = Context + Action + Validation。

## Step 1 —— 读约定
- **Context**：先对齐宪法，判断层级与安全红线。
- **Action**：读 `openspec/agreement.md`；本 change 属 config/core/tools/agent/api 多层的并发优化，不触碰安全红线（SQL 校验/HITL/任意代码执行默认关不动），可能命中 Avoid（不造重复实现 → db_max_overflow 不假实现；缓存必须有界 → 保持有界不变）。
- **Validation**：在 proposal.md 已写明分层与 Avoid 应对。 `[x]`

## Step 2 —— 配置参数化（config/settings.py）
- **Context**：池大小与 uvicorn 参数去硬编码，便于压测调参。
- **Action**：`settings.py` 新增 `db_pool_min_size=5`、`db_pool_size` 默认 10→20、`tool_thread_pool_size=4`、`api_backlog=2048`、`api_keepalive=5`、`api_graceful_shutdown=30`；`db_max_overflow` description 标 deprecated。
- **Validation**：`py -c "from config.settings import get_settings as g; s=g(); print(s.db_pool_min_size, s.db_pool_size, s.tool_thread_pool_size, s.api_backlog, s.api_keepalive, s.api_graceful_shutdown)"` 输出 5 20 4 2048 5 30。 `[ ]`

## Step 3 —— 去硬编码（core/database/pool.py + 三 tools）
- **Context**：消灭硬编码 min_size=5 与三处 max_workers=2。
- **Action**：`pool.py` 用 `settings.db_pool_min_size`；`analysis_tools.py`/`chart_tools.py`/`chart_sandbox.py` 三处 executor 用 `get_settings().tool_thread_pool_size`。
- **Validation**：`grep -rn "max_workers=2\|min_size=5" core tools utils` 无残留硬编码值。 `[ ]`

## Step 4 —— 补并发安全（agent/analyst_agent.py）
- **Context**：并发冷启动真洞，多个 coroutine 重复 create_async_agent。
- **Action**：`AnalystAgentFactory` 加 `_async_agent_pending: Dict[Any, asyncio.Task]`；`get_cached_async_agent` 实现 futurization（命中缓存直接返回 / pending 同名 await 复用 / 否则包 task 存 pending await 后移入缓存清理 / 失败清 pending）；同步版加 `threading.Lock`。
- **Validation**：`tests/test_agent_cache_concurrency.py` 并发冷启动只创建一次、失败清 pending 通过。 `[ ]`

## Step 5 —— 结果缓存注释（utils/result_store.py + tools/chart_tools.py）
- **Context**：单 loop 下无真争用，不加锁只加注释说明。
- **Action**：在 result_store 与 chart_tools `_spec_cache` 附近加注释：跨协程内存引用如需多 worker 共享须 Redis；序列化若进线程池再加 threading.Lock。
- **Validation**：注释存在且无行为变更。 `[ ]`

## Step 6 —— uvicorn 调参 + /api/stats（api/main.py run_server.py api/routes.py）
- **Context**：透传 backlog/keepalive/graceful，并暴露池态供压测闭环。
- **Action**：`main()` 与 `run_server.py` 的 uvicorn.run 加 `backlog=api_backlog, keepalive/keepalive_timeout=api_keepalive (uvicorn 0.34+), graceful_shutdown_timeout=api_graceful_shutdown`；新增 `GET /api/stats` 返回 `db_pool.get_stats()` + 缓存/线程池状态。
- **Validation**：起服务后 `curl /api/stats` 返回 size/min/max/idle。 `[ ]`

## Step 7 —— 压测包 bench（bench/__init__.py + bench/loadtest.py）
- **Context**：可复用并发压测 CLI。
- **Action**：按 plan 实现 `py -m bench.loadtest`（httpx + asyncio.Semaphore + perf_counter + statistics；CLI 参数齐全；endpoint=query 有 cost 警告；`--dry-run` 只打印计划）。
- **Validation**：`py -m bench.loadtest --dry-run` 打印计划退出 0。 `[ ]`

## Step 8 —— 单测
- **Context**：本仓库测试是硬门槛。
- **Action**：新增 `tests/test_settings_defaults.py`、`tests/test_agent_cache_concurrency.py`、`tests/test_loadtest_cli.py`。
- **Validation**：`py -m pytest tests/ -q` 全绿（新增前 99 + 新增用例）。 `[ ]`

## Step 9 —— 压测冒烟
- **Context**：验证脚本真能压、池态可观测。
- **Action**：起服务 → `py -m bench.loadtest --endpoint health --concurrency 50 --requests 200` 看 QPS/池态；如需压 query 用 `--thread-mode unique` 少量。
- **Validation**：脚本无异常退出，输出含 QPS/latency 分位；/api/stats 池态合理。 `[ ]`

## Final —— 收尾自检
- 对照 overview How 逐条核对兑现。
- 更新 `README.md`（bench 用法 + 新配置）、`CHANGELOG.md`（记录性变更）。
- 本 change 目录移出 `changes/`（归档至 `openspec/archived/`）。
- 提交中文一句主题，如 `git commit -m "feat(并发)：新增压测 bench 与并发能力提升(<取舍>)：..."`，附 Co-Authored-By。 `[ ]`
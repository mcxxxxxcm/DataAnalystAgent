# Change Proposal：并发压测与并发能力提升

> 设计文档，给 review 用。依据 approved plan 整理，引用真实文件路径。

## 方案

**现状** → **目标** → **改动清单**。

### 1. 配置参数化（config/settings.py）

**现状**：
- `db_pool_size` 默认 10；`db_max_overflow=20` 定义但从未使用（asyncpg 无 overflow）
- `core/database/pool.py` `create_pool(min_size=5)` 硬编码
- 三处 `ThreadPoolExecutor(max_workers=2)`：`analysis_tools.py:28` `chart_tools.py:21` `chart_sandbox.py:25`

**改动**：
- 新增 `db_pool_min_size: int = 5`（ge=1 le=100）
- `db_pool_size` 默认 10→20（le=100 不变）
- 新增 `tool_thread_pool_size: int = 4`（ge=1 le=32）
- `db_max_overflow` description 标 deprecated（`extra="ignore"` 下删除会被静默忽略，故保留字段）

### 2. 去硬编码（core/database/pool.py + 三 tools）

- `pool.py` `min_size=5` → `settings.db_pool_min_size`
- 三处 executor `max_workers=2` → `get_settings().tool_thread_pool_size`

### 3. 补并发安全（agent/analyst_agent.py）

**现状**：`get_cached_async_agent()` 无锁，并发冷启动时多个 coroutine 见 `name not in _async_agent_cache`，各自 `create_async_agent()` 重复创建。
**改动（futurization）**：
- 新增 `_async_agent_pending: Dict[Any, asyncio.Task]`
- 命中缓存直接返回；pending 同名则 await 复用；否则包 task 存 pending、await 后移入缓存并清理，失败清 pending 防悬挂
- 同步版 `get_cached_agent` 加 `threading.Lock`

结果缓存（`result_store.py` / `chart_tools.py._spec_cache`）：单 loop 同步 dict 操作无真争用，只加注释说明不加锁（将来若序列化进线程池再改 `threading.Lock`）。

### 4. uvicorn 调参 + /api/stats

- 新增 `api_backlog=2048`、`api_keepalive=5`、`api_graceful_shutdown=30`
- `api/main.py` 的 `main()` 与 `run_server.py` 透传（run_server 仍是 app 对象路径，不传 workers）
- 新增 `GET /api/stats`：返回 `db_pool.get_stats()` + 缓存/线程池状态

### 5. 压测包 bench/

- `bench/__init__.py` + `bench/loadtest.py`，入口 `py -m bench.loadtest`
- httpx.AsyncClient + asyncio.Semaphore + statistics；不支持 aiohttp/locust（未装）
- CLI：`--endpoint{health,ping,query}` `--target` `--concurrency` `--duration|--requests` `--query|--query-file` `--thread-mode{unique,reuse,per-worker}` `--token` `--timeout` `--report-interval` `--json` `--dry-run`
- endpoint=query 启动先打印费用/耗时警告；三种 thread-mode 语义见 plan

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| db_max_overflow | 废弃保留不实现 | asyncpg 无 overflow；假实现违反 Avoid#4 | 字段变 dead（但 extra=ignore 下删了也会被 env 静默忽略） |
| db_pool_size | 10→20 | sql_timeout=30 时慢查询占连接最多 30s，20 并发需 20 连接；池满 acquire 排队天然节流 | 连接资源占用上升（需对 pg_stat_activity） |
| 结果缓存锁 | 不加锁只加注释 | 单 loop 同步 dict 操作无真争用；asyncio.Lock 只增开销 | 若将来序列化进线程池需补 threading.Lock |
| agent 缓存 | futurization | 消除并发冷启动重复创建 | 需维护 pending task 生命周期 |
| uvicorn workers | 默认仍 1 | win32 多 worker spawn 有坑；run_server app 对象不支持多 worker | 单 worker 不吃满多核（后续可反向代理多端口） |
| base_url 压测 | 真实 /query | 用户明确真实 Postgres/LLM | LLM 调用成本高（脚本内置 cost 警告 + dry-run） |

## 兼容性

- 所有改动不破坏现有 API 响应与前端字段；`/api/stats` 为新增只读端点。
- 配置项全带默认值，向后兼容；`db_pool_size` 默认值变化不影响功能语义。
- 短期记忆走 AsyncPostgresSaver 持久化，即使将来多 worker 跨进程仍可用（本项目本次不改 worker 默认）。

## 测试计划

- `tests/test_settings_defaults.py`：新配置默认值断言（db_pool_min_size=5, db_pool_size=20, tool_thread_pool_size=4, backlog/keepalive/graceful）
- `tests/test_agent_cache_concurrency.py`：并发冷启动只创建一次、失败清 pending
- `tests/test_loadtest_cli.py`：CLI 参数解析（默认值、互斥、query 必填项、dry-run）
- 全量 `py -m pytest tests/ -q` 全绿
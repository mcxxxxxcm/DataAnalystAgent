# Change Overview：并发压测与并发能力提升

## Why（为什么做）

当前系统没有压测设施，且存在多处已确认的并发瓶颈：连接池/线程池大小硬编码、agent 缓存并发冷启动重复创建、uvicorn 无 backlog/keepalive 调参、无可观测的池态端点。用户要对真实 Text2SQL 全链路做压测并提升并发能力。

## What（做什么 / 不动什么）

**做**：
- 新增可复用压测包 `bench/`（httpx + asyncio，压 /health 或真实 /query）
- 连接池 `min_size` 去硬编码、`db_pool_size` 默认 10→20、三处线程池大小配置化
- 修复 `agent` 缓存并发冷启动真洞（futurization），补并发安全
- uvicorn `backlog/keepalive/graceful_shutdown` 参数化（默认仍单 worker）
- 新增只读 `GET /api/stats` 可观测端点

**不做**：
- 不做 `db_max_overflow` 假实现（asyncpg 无 overflow 概念，废弃保留）
- 不加 Redis 转多进程共享缓存（`redis_url` 已存在但默认 None，属于后续演进）
- 不加 JSON 序列化线程池（先测后加）
- 不抬高 uvicorn worker 默认值（多 worker 在 win32 有 spawn 风险，保持单 worker）

影响层：config / core / tools / agent / api + 新增 bench 包。

## How（怎么落地,一句概览）

去硬编码配置化池大小 → 修复 agent 缓存并发 → 新增 bench 压测包与 /api/stats → uvicorn 调参透传 → 加单测并全量回归。

---

- 关联模块：config/settings.py, core/database/pool.py, agent/analyst_agent.py, tools/*.py, api/routes.py
- 涉及测试：tests/test_loadtest_cli.py, tests/test_agent_cache_concurrency.py, tests/test_settings_defaults.py
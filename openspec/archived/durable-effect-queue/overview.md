# Change Overview：持久化 Effects 队列 + 指数退避（Durable Effect Queue & Backoff）

> 迁移 dsh-superagent `Effects`（`src/app/effects.ts`）的句型：副作用入**按 key 幂等**的队列，**指数退避 + 抖动**重试、带最大尝试次数与健康监测；本 change 落地为可复用的异步原语并接通 SQL 瞬时错误路径。

## Why（为什么做）

当前 SQL 瞬时错误靠 `ToolRetryMiddleware` 在**单轮内同步重试**：同一 key 无去重、无退避、不跨调用生存、失败即放弃。dsh 的效果队列能「按 key 合并去重 + 指数退避 + 持久化 + 失败健康标记」，让瞬时失败更稳、更省、且可观测，但本项目缺这个原语。

## What（做什么 / 不动什么）

- **新增** `utils/effect_queue.py`：`AsyncEffectQueue`。
  - `enqueue(kind, key, coro_fn, *args, max_attempts, base_delay)`：按 `(kind,key)` 幂等合并——同 key 待处理时**替换 payload 并立即到期**（对齐 dsh "enqueuing the same key replaces payload and makes it due"）。
  - 指数退避：`base_delay × 2^(attempt)` 封顶 + 少量抖动；`max_attempts` 内失败递增，超限标记失败健康。
  - 持久化：`persist_path`（可选 JSONL）落盘待处理项，进程重启后可恢复（durable）；`persist=False` 为内存模式。
  - `process()` 一次取「到期」任务执行，成功 settle / 失败按退避重排；提供 `pending()` 供可观测。
- **修改** `config/settings.py`：`effect_queue_max_retries=2`、`effect_queue_base_delay=1.0`、`effect_queue_persist= False`（+`effect_queue_persist_path` 可选，默认 `None` 用临时目录）。
- **修改** `core/database/pool.py`（或 `tools/sql_tools.py`）：SQL **瞬时**错误路径经 `run_sql_durable(coro_fn, key=规范化SQL)` 走效果队列退避重试（门控 `effect_queue_max_retries>0`，默认开但仅作为 ToolRetryMiddleware 之外的**跨调用退避**补充，不替换其轮内重试）。
- **测试** 新增 `tests/test_effect_queue.py`。
- **不做**：不引入 Redis/DB 做队列存储（JSONL 已够「持久」）；不改变 `ToolRetryMiddleware` 语义；不动非瞬时错误处理。

## How（怎么落地，一句概览）

写 `AsyncEffectQueue`（key 幂等 + 指数退避 + 可选 JSONL 持久化），单测到行为稳固，再在 SQL 瞬时错误路径加一个走队列的 `run_sql_durable` 辅助并接通。

---

- 关联模块：`utils/` · `core/database/pool.py` · `config/settings.py`
- 关联 CAP：CAP-DB-001（超时执行）· CAP-AGENT-005（瞬时重试）· CAP-SEC-005（SQL 错误分类）
- 涉及测试：`tests/test_effect_queue.py`（新增）；现有 138 项保持通过
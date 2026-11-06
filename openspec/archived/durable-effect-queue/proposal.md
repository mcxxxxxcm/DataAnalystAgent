# Change Proposal：持久化 Effects 队列 + 指数退避

> 设计文档。迁移 dsh `Effects` 句型的「key 幂等 + 指数退避 + 持久化 + 健康」。

## 方案

### 现状
- `middleware/config.py` 的 `ToolRetryMiddleware` 对瞬时错误做**轮内同步重试**（`max_retry_attempts=3`），结束后失败即放弃；无按 key 去重、无退避、不跨调用/进程生存，失败过程不可观测（仅日志）。
- SQL 错误分类已有 `is_transient_error`（`core/security/sql_error.py`），可复用做「瞬时」判定。

### 目标
- 提供通用 `AsyncEffectQueue` 原语：key 幂等合并、指数退避+抖动、最大尝试、可选 JSONL 持久化、pending 可观测。
- 接通 SQL 瞬时路径：瞬时失败进入队列退避重试（跨调用、持久），作为现有轮内重试的**补充层**，不替换其语义。

### 改动清单
- **新建** `utils/effect_queue.py`
  - `@dataclass _Effect`: `kind,key,fn,args,kwargs,max_attempts,base_delay,next_due,attempts,backoff`.
  - `class AsyncEffectQueue`:
    - `__init__(self, persist_path: Optional[str]=None)`：加载 JSONL 持久化已存 effect。
    - `async enqueue(kind, key, fn, *args, max_attempts:=3, base_delay:=1.0, **kwargs)`：已存在同 `(kind,key)` 且未 settle → 替换 fn/args、`next_due=now`（立即到期）；否则新加。写入持久化。
    - `async process()`：取 `next_due<=now` 且未达 `max_attempts` 的任务按到期排序逐个执行；成功 settle 并落地；瞬时失败 → `attempts+=1`、`next_due = now + base_delay * 2**(attempts) + jitter`；失败健康计数。
    - `pending()`/`settled()`/`failed()`：只读可观测；`sweep()` 清理已 settle/遗弃项（有界）。
    - 线程/协程：单事件循环下同步 dict 维护 + enqueue/process 异步化，不加锁（复用项目注释口径）。
  - 提供 `def run_sql_durable(fn)` async 装饰/包装：`is_transient_error` 判定内，把可重试执行包装进队列（key=规范化SQL 的哈希）并 `await process()`。
- **修改** `config/settings.py`：`effect_queue_max_retries:int=2(ge=0)`、`effect_queue_base_delay:float=1.0(ge=0.1)`、`effect_queue_persist:bool=False`、`effect_queue_persist_path:Optional[str]=None`（为 `None` 且 persist=True 时用 `logs/effect_queue.jsonl`）。
- **修改** `core/database/pool.py`：在 `fetch`/`execute` 的瞬时异常分支，若 `effect_queue_max_retries>0` 则经 `run_sql_durable` 退避重试（保留原抛错兜底），否则维持现状。
- **测试** `tests/test_effect_queue.py`：key 幂等合并、退避递增、max_attempts 超限失败、JSONL 持久化重启恢复、pending/settled 计数、`is_transient_error` 走队列而无关 SQL 不走。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| JSONL vs Redis/DB 持久 | JSONL 追加写 + 恢复 | 零新增依赖、满足「重启可恢复」的持久语义 | 单进程级持久，不跨 worker 共享（多 worker 见 backlog B006） |
| 走队列作为补充层 vs 替换轮内重试 | 补充层 | 降低风险，ToolRetryMiddleware 语义与既有测试保持不变 | 两套重试并存，需文档说明职责 |
| 默认 `effect_queue_max_retries=2` | 开但小 | 接通真实路径又不激进；可在压测中调 | 新配置项 |

## 兼容性
- 新增配置均有默认值；`effect_queue_max_retries=0` 时退避层完全关闭，行为与现状一致。
- `result`/`exception` 语义不变：队列内瞬时重试仍向上抛最终异常，不吞错。
- 既有 `tests`（含 retry 相关）保持通过。

## 测试计划
- `tests/test_effect_queue.py`：key 合并/退避/超限/持久/计数器/瞬时判定。
- `py -m pytest tests/ -q` 全绿。
# 状态所有权（One-Writer-Per-State）

> 迁移 dsh-superagent `core` 的纪律：**每类可变状态只允许一个写入者，其余读取或委托该写入者**；
> **读查询绝不写**（对齐其 store-read「never write」）。本表是项目各内存/持久状态的唯一写者约定。
> 单文件来源（不重复抄到别的文档，见 agreement §6）；改此表时同步改影响它的 change。

## 约定要点

- **读不写**：`get`/`peek` 读路径不得删除/修改条目（过期惰性回收例外，且回收属缓存自身写职责）。
- **单一写者**：改状态只能经由表中「唯一写者」提供的接口；其余模块只读。
- 一致性：本表仅记录「谁是写者 / 何时写」，细节能力以 `openspec/specs/spec.md`（CAP-*）为准。

## 状态 → 写者 表

| 状态 | 唯一写者 | 读口 | 备注 |
|------|----------|------|------|
| 查询结果缓存（result_id） | `utils/result_store.py`（代理到 `BoundedTTLCache`） | `get_result`（只读）；`set_result`/`clear` 写 | 有界 50 / TTL 10min，常量见 `utils/bounded_cache.py` |
| 图表 spec 缓存（option_id） | `tools/chart_tools.py`（代理到 `BoundedTTLCache`） | `get_cached_spec`（只读，非摧毁）；`_store_spec` 写 | 有界 50 / TTL 10min；/chart/option 读已改非摧毁式 |
| schema 表结构缓存 | `core/database/schema.py`（`SchemaManager`） | `get_table_schema`；写 `_cache` | TTL 3600 属该模块成员常量（少设置：不进配置） |
| schema 检索索引 | `core/database/schema.py`（`_get_index`） | `get_relevant_schemas` | `clear_cache` 后惰性重建 |
| agent 实例缓存 | `agent/analyst_agent.py`（`AnalystAgentFactory`） | `get_cached_agent`/`get_cached_async_agent`；写 `_agent_cache` | 上下文无关的 agent 实例可复用 |
| 短期记忆 checkpointer | `middleware/config.py`（`get_async_checkpointer`/`setup_checkpointer`） | 读由 LangGraph 代理 | 优先 AsyncPostgresSaver，失败回退 InMemory |
| 长期记忆 Store | `middleware/config.py`（`get_store`/`setup_store`） | `memory_tools` 读写 | 静默降级，记忆非强依赖 |
| 本地日志/审计 | `middleware/local_logger` | `query_records`/`get_recent_records` | 追加写 |

## 新增状态的约定

新增内存缓存一律：
1. 用 `utils/bounded_cache.py::BoundedTTLCache`（单一写者原语），勿再手写 dict+expiry（Avoid §4）；
2. 读接口非摧毁式（`get`/`peek`），确要一次性消费才用 `pop`；
3. 在新增 change 中把新状态补进上表，再回填 `spec.md` CAP 与 `tasks.md` TASK。
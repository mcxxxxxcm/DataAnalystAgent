# Change Proposal：单一写者纪律审计

> 设计文档。迁移 dsh「one writer per state」「Read queries never write」。

## 方案

### 现状
- `utils/result_store.py`（第 16-19 行）与 `tools/chart_tools.py`（第 32-35 行）各自实现 `_store/_expiry + TTL + max_entries`，逻辑重复。
- `chart_tools.get_cached_spec`（第 50-59 行）用 `_spec_cache.pop(chart_id, None)` 读取——读会删除条目；`api/routes.get_chart_option` 经它取 spec，一旦删除，同 id 再取不到（对多读/重试不友好），也违反「读不写」。
- 两处 TTL 常量独立维护，易分叉。

### 目标
- 单一写者：缓存状态由 `BoundedTTLCache` 一个类拥有写路径；读路径不改变状态（过期惰性回收除外，且回收属缓存自身写原语职责）。
- 消除重复缓存实现。
- 「谁写什么」有文档 + 单测兜底。

### 改动清单
- **新建** `utils/bounded_cache.py`
  - `BoundedTTLCache(max_entries=50, ttl_seconds=600)`：`set(key,value)`（写，超上限淘汰 `min(expiry)` 最早项）、`get(key)`（只读 peek，过期返回 None 并惰性回收）、`pop(key)`（一次性读取并删除，供真正一次性消费）、`size()`、`clear()`。内部用两个 dict，单写原语集中在类内。
  - 线程/协程说明沿用现有注释：单事件循环下同步 dict 无真争用，不加锁。
- **修改** `utils/result_store.py`：全局 `_cache = BoundedTTLCache(...)`；`set_result`/`get_result`/`clear`/`cache_size` 委托其上，模块导出的函数签名不变。
- **修改** `tools/chart_tools.py`：`_spec_cache = BoundedTTLCache(...)`；`_store_spec`→`set`；`get_cached_spec`→`get`（非摧毁）；自定义图一次性消费若需删除则显式 `pop`，但 `/chart/option` 读改走 `get`。
- **新建** `docs/state-owners.md`：一张状态所有权表（result_store/chart_spec/schema 缓存/agent 缓存/checkpointer/store/本地日志），每项列唯一写者与读写约定。
- **修改** `openspec/design.md`：加一节指针指向 `docs/state-owners.md`（遵循 agreement §6 单一来源，不重复内容）。
- **测试** `tests/test_bounded_cache.py`（容量/淘汰/TTL/只读 get 不删/pop 删）+ `tests/test_single_writer.py`（断言：`get_cached_spec` 读后条目仍在；调用 `get` 不改变 cache_size）。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 内聚一个缓存原语 vs 各自维护 | 收敛为一个 `BoundedTTLCache` | 消除重复实现（Avoid §4）、单点改 TTL/淘汰策略 | 一次重构，需回归两处调用方 |
| 读路径非摧毁 | `get` 只读 / `pop` 显式删除 | 满足「读不写」，避免多读/重试丢 spec | 个别一次性消费点需显式 `pop` |
| 不动 schema/agent 缓存 | 本轮仅收敛重复的两处 | 控制风险与范围（存量缓存各自有主） | schema TTL 3600 暂不与统一原语接 |

## 兼容性
- `result_store` / `chart_tools` 对外函数签名与返回不变；`option_id`/`result_id` 语义不变。
- `/chart/option` 读由摧毁式改为只读，行为更强（重试仍可取到），不破坏前端。
- TTL 常量保持 600（与现状一致），不改变过期行为。

## 测试计划
- `tests/test_bounded_cache.py`：新增用例。
- `tests/test_single_writer.py`：断言读不写、各缓存唯一写者约定。
- `py -m pytest tests/ -q` 全绿。
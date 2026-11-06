# Change Overview：单一写者纪律审计（One-Writer-Per-State）

> 迁移 dsh-superagent `core` 的「每类状态只允许一个写入者，其余只读或委托」+「读查询绝不写」纪律，审计并修正本项目内存缓存的状态所有权与读-改副作用。

## Why（为什么做）

`result_store` 与 `chart_tools` 各手写一套「bounded dict + expiry」缓存（重复实现，Avoid §4），且 `chart_tools.get_cached_spec` 用 `.pop()` 读取——**读路径会删缓存条目**（摧毁式读），违反「读不写」；两处 TTL 常量又不统一（600 vs 600，但 schema 用 3600），单点维护难。

## What（做什么 / 不动什么）

- **新增** `utils/bounded_cache.py`：一个**单一写者**的有界 TTL 缓存原语 `BoundedTTLCache`（写：`set`；读：`get` 只读；过期回收由写原语内部负责；peek 不删）。
- **修改** `utils/result_store.py`、`tools/chart_tools.py`：改用 `BoundedTTLCache`，消除重复缓存实现；`get_cached_spec` **非摧毁式读取**（新增显式 `pop` 供真正需要的一次性消费）。
- **新增** `docs/state-owners.md`：列出每类可变状态及其唯一写者（对齐 dsh 的 one-writer 表），并在 `openspec/design.md` 加指针。
- **测试** 新增 `tests/test_bounded_cache.py` + `tests/test_single_writer.py`。
- **不做**：不动 `schema_manager`/`agent_factory` 现有缓存（本轮只收敛复制粘贴的两处）；不引入 Redis（留 backlog B006）。

## How（怎么落地，一句概览）

抽象 `BoundedTTLCache`（唯一写者实现），替换 `result_store` 与图表 spec 缓存；把图表读路径改成非摧毁式，并用「读不写」断言单测兜底。

---

- 关联模块：`utils/` · `tools/chart_tools.py` · `core/database/schema.py`(参考) · `openspec/design.md`
- 关联 CAP：CAP-UTIL-001 · CAP-AGENT-003（缓存有界）· CAP-API-007
- 涉及测试：`tests/test_bounded_cache.py`·`tests/test_single_writer.py`（新增）；现有 138 项保持通过
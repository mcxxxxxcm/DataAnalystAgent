# Change Overview：少设置 / 默认优先（Few-Settings Audit）

> 迁移 dsh-superagent 哲学「A default replaces a setting when one value suits almost every team. Behaviour described in words is prompt text, not a setting.」——清扫 `config/settings.py` 中无消费方/半死的配置项，收敛单一来源。

## Why（为什么做）

审计发现若干配置项在代码中**无任何消费方**（`cache_ttl`、`redis_url`、`agent_verbose`），`db_max_overflow` 已废弃仅被测试引用。它们造成「配了没用」「TTL 各自写死（schema 3600 / result_store 600）」的迷惑与漂移，违背少设置原则且增加维护与误配风险。

## What（做什么 / 不动什么）

- **删除 4 个无用/废弃配置项**：`cache_ttl`、`redis_url`、`agent_verbose`、`db_max_overflow`，并更新引用它们的测试与文档。
- **收敛 TTL 单一来源**：`result_store`/图表缓存 TTL 在 (B) 的 `BoundedTTLCache` 里以常量为唯一来源；不为此新设配置。
- **文档**：在 `config/settings.py` 顶部与 `docs/state-owners.md` 记录「TTL 常量即配置」约定。
- **测试** 更新 `tests/test_settings_defaults.py`（移除 `db_max_overflow` 断言，改断言新默认）。
- **不做**：不改动了 `llm_context_window`/`base_url`/`api_reload` 等在用的配置；不新增「行为性」配置（行为交给 Change A 的 prompt-text 直答）。

## How（怎么落地，一句概览）

逐一确认四个配置无真实消费方后删除，修测试与文档，跑全绿；把 TTL 单一来源约定写进 (B) 的缓存原语与状态所有权文档。

---

- 关联模块：`config/settings.py` · `utils/bounded_cache.py`(B) · `docs/state-owners.md`(B)
- 关联 CAP：CAP-CONF-002（配置完备）
- 涉及测试：`tests/test_settings_defaults.py`（更新）
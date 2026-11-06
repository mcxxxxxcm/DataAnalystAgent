# Change Recipe：少设置 / 默认优先（执行剧本）

## Step 1 —— 读约定
- **Context**: 本 change 落 `config` 层，属清理，不触安全/运行时行为。
- **Action**: 读 `openspec/agreement.md`；确认删除配置不破坏分层。
- **Validation**: 已确认属 `config` 清理、不影响安全红线。 `[ ]`

## Step 2 —— 核对死配置证据
- **Context**: 删除前先证实「无消费方」，避免误删在用配置。
- **Action**: grep `cache_ttl` / `redis_url` / `agent_verbose` / `db_max_overflow` 在 `--include=*.py` 的引用；记录当前仅 `tests/test_settings_defaults.py` 引用 `db_max_overflow`。
- **Validation**: 结果与 proposal「现状（审计证据）」一致；非 `settings.py`/测试的引用为 0。 `[ ]`

## Step 3 —— 删除配置项
- **Context**: 移除死配置，收敛单一来源。
- **Action**: 删除 `config/settings.py` 中 `db_max_overflow`、`cache_ttl`、`redis_url`、`agent_verbose`；顶部注释补一条「运行时一次性/常量参数以模块常量为准，不进设置」。
- **Validation**: `Settings` 不再有这四个属性（`hasattr(Settings(), ...) is False`）。 `[ ]`

## Step 4 —— 更新测试与文档
- **Context**: 修断言防回潮；README 若提及则同步。
- **Action**: 更新 `tests/test_settings_defaults.py`：删 `test_db_max_overflow_deprecated_but_kept`，新增 `test_dead_settings_removed`（断言四者 `not hasattr`）。grep 更新 `README.md`/设计文档中对 `redis_url`/`cache_ttl` 的提及。
- **Validation**: `py -m pytest tests/ -q` 全绿。 `[ ]`

## Final —— 收尾自检
- overview How 逐条兑现；更新 `CHANGELOG.md`（删除废弃配置属可记录变更）；本 change 目录移至 `openspec/archived/`。 `[ ]`
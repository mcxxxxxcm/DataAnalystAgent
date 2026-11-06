# Change Proposal：少设置 / 默认优先

> 设计文档。迁移 dsh「few settings / defaults-over-settings」。

## 方案

### 现状（审计证据）
用 grep 核实 `config/settings.py` 字段引用：
- `agent_verbose`（第 163 行）：**0 处引用** → 死配置，删除。
- `cache_ttl`（第 70 行，默认 3600）：**0 处引用**；实际 TTL 由 `result_store`(600) / `chart_tools`(600) / `schema.py`(写死 3600) 各自常量决定 → 半死且误导，删除，TTL 交由缓存原语单一来源。
- `redis_url`（第 69 行）：**0 处引用**（仅注释/README 提及「预留 Redis」，但 Redis 无实现）→ 为不存在的能力预留配置，违背少设置，删除（多 worker 共享仍需时见 backlog B006，届时再引入）。
- `db_max_overflow`（第 52-55 行）：已标废弃，仅 `tests/test_settings_defaults.py` 引用 → 删除字段 + 更新测试。`extra="ignore"` 让 `.env` 中同名旧变量被安全忽略，无兼容风险。

### 目标
- `config/settings.py` 仅含真实被消费的配置；每个配置有且仅有一个作用。
- TTL 类「配置」收敛为缓存原语的模块常量单一来源，不碎片化。

### 改动清单
- **修改** `config/settings.py`：删除 `db_max_overflow`、`cache_ttl`、`redis_url`、`agent_verbose`；顶部注释补一句「运行时一次性/常量类参数（如缓存 TTL）以模块常量为准，不进设置」。
- **修改** `tests/test_settings_defaults.py`：删除 `test_db_max_overflow_deprecated_but_kept`；`test_concurrency_defaults` 不动。
- **修改** `README.md`：若 `redis_url`/`cache_ttl` 被 README 提及则更新（grep 核对）。
- **测试**：保持全绿；新增一条断言「删除项不再存在于 Settings 模型」（防回潮）。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 删 `redis_url` vs 保留预留 | 删除 | 无 Redis 实现，预留违背少设置；真上 Redis 时再引入（backlog B006） | 多 worker 近期仍跨进程不共享缓存（现状已如此） |
| 删 `cache_ttl` vs 接线 | 删除，TTL 归缓存原语常量 | 现在没人接，接线是「造需求」；原语单点可调 | TTL 不能靠 env 改（如需可后加） |
| `.env` 旧变量 | 依赖 `extra="ignore"` 忽略 | 兼容性最佳 | 用户可能以为配了生效（文档注明） |

## 兼容性
- 删除字段均为无消费方/已废弃项，代码正常路径不引用；`Settings(...)` 不再有这些属性，`tests` 同步更新。
- `.env` 中同名变量被 `extra="ignore"` 安全忽略，不报错。

## 测试计划
- `tests/test_settings_defaults.py`：更新为保证无删除项残留（`not hasattr`）。
- `py -m pytest tests/ -q` 全绿。
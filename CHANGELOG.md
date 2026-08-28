# Changelog

本文档记录本项目的所有重要变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的惯例。

## [1.1.0] - 2026-08-28

### 安全加固（P0）

- **新增可选 API 鉴权**
  - `api/main.py`：新增全局 HTTP 中间件，当配置 `API_AUTH_TOKEN` 时要求所有 `/api/**` 请求携带 `Authorization: Bearer <token>`，否则返回 401。未配置时不鉴权（默认放开，便于本地开发）。
  - 使用 `secrets.compare_digest` 做恒定时间比较，避免时序侧信道。
  - `config/settings.py`：新增 `api_auth_token`（默认空）。

- **修复 CORS 配置风险**
  - `api/main.py`：`allow_origins` 从写死的 `["*"]` 改为读取 `CORS_ORIGINS`（逗号分隔）。
  - 当来源为通配符 `*` 时自动禁用 `allow_credentials`，避免 `[*] + credentials=True` 的不安全组合；配置了具体来源时才允许携带凭据。
  - `config/settings.py`：新增 `cors_origins` 及其解析属性 `cors_origin_list` / `is_cors_open`。

- **沙箱超时真正生效**
  - `utils/chart_sandbox.py`：`execute_chart_code()` 原先声明的 `timeout` 参数并未使用，`exec` 可被死循环代码卡死。现改为在独立线程池中执行绘图代码，通过 `future.result(timeout=...)` 真正限制执行时长，超时立即关闭 figure 并返回错误。

- **默认关闭任意代码执行**
  - `tools/__init__.py`：`create_custom_chart`（允许 LLM 生成并执行任意 Python 绘图代码）默认不加入 `ALL_TOOLS`，需在 `.env` 设置 `ENABLE_CUSTOM_CHART=true` 才暴露。
  - `config/settings.py`：新增 `enable_custom_chart`（默认 `false`）。

### 架构与可靠性（P1）

- **移除系统提示词中的硬编码示例表**
  - `agent/prompts.py`：删除写死的 `sales/orders/order_items/products/users` 及具体 SQL 示例，改为指导 LLM 以 `get_relevant_schemas` 返回的真实结构为准，避免与真实库不一致误导模型。

- **图表缓存改为有界 + TTL**
  - `tools/chart_tools.py`：原先无界的全局 `_chart_cache` 改为带过期时间（默认 10 分钟）与容量上限（默认 50 条）的有界缓存，超限自动淘汰最旧条目，防止内存无界增长。

- **SQL 超时读取配置**
  - `tools/sql_tools.py`：`query_database` 原先硬编码 `timeout=30`，现改为使用 `settings.sql_timeout`。

- **修复孤儿 checkpoint 清理依赖不存在的表**
  - `utils/checkpoint_cleanup.py`：`cleanup_orphaned_checkpoints` 原先 `LEFT JOIN conversations`，但应用从不创建该表，运行时必然报错。现先检测 `conversations` 表是否存在，不存在则跳过并给出明确提示。

- **删除重复实现**
  - 删除 `tools/viz_tools.py`（`create_*_chart` 与 `chart_tools.create_chart` 功能重叠，且从未纳入 `ALL_TOOLS`，为死代码）。
  - `tools/chart_tools.py`：新增 `warmup_matplotlib()`，承接启动预热逻辑；`api/main.py` 中对应 import 已更新。
  - `tools/__init__.py`：移除对 `viz_tools` 的引用。

### 性能与体验（P2）

- **合并重复的图表提取逻辑**
  - `api/routes.py`：抽取公共助手 `resolve_chart_image()`，统一处理 `chart_id:` 前缀 → 真实 base64 的解析，并精简 `extract_chart_data` / `extract_all_chart_data` 的重复代码。

- **uvicorn 热重载走配置**
  - `api/main.py`：`reload` 从写死的 `True` 改为读取 `API_RELOAD`（默认 `false`），生产环境默认关闭。

### 工程化（P3）

- **可选依赖延迟导入**
  - `core/__init__.py`：`db_pool` / `schema_manager` 与 security 模块一样改为延迟导入，降低启动耦合，也使得 `core/security` 等纯逻辑模块可在不安装全部重依赖（asyncpg 等）时被单元测试。

- **新增单元测试**
  - 新增 `tests/test_security.py`：覆盖 `SQLValidator`（白名单/黑名单/写权限/禁止函数/多语句注入）、`SQLSanitizer`（自动 LIMIT/危险注释移除）、`RiskAssessor`（写操作/无 WHERE 写操作为 CRITICAL/安全 SELECT）。共 14 个用例，`pytest tests/test_security.py` 运行。

- **pydantic v2 现代化**
  - `config/settings.py`：弃用的 `class Config` 改为 `model_config = SettingsConfigDict(...)`，消除 PydanticDeprecatedSince20 告警。

### 其他

- `api/main.py`：应用版本号升至 `1.1.0`。
- `.env`：以注释形式补充新增配置项（`API_AUTH_TOKEN` / `CORS_ORIGINS` / `ENABLE_CUSTOM_CHART` / `API_RELOAD`）供参考启用。
- `README.md`：同步更新配置表、已知问题处理状态。

### 已知遗留 / 待后续版本

- `get_relevant_schemas` 仍基于硬编码关键词映射，表多时召回不可靠，建议后续改为基于 Embedding 的语义检索。
- 同步版 `create_agent` 缺少消息裁剪中间件（仅异步版本有），长对话可能 token 超限，建议两端统一。
- 未接入 LLM prompt 缓存，相同系统提示词每次全量计费，后续可启用缓存。
- 缺少统一指标与分布式追踪、CI 流水线尚未落地。

---

[1.1.0]: 首个梳理后版本：安全加固 + 架构治理 + 可测试性提升。
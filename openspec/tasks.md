# 任务分解（Tasks）

> 项目级任务清单，给**执行 / 验收**用，回答「要拆成哪些可验收的任务、谁负责、怎么验收」。
> 编号规则：`TASK-xxx`。状态：`[done]` 已实现 / `[todo]` 候选未做（对齐 `specs/spec.md` 状态表与 `agreement.md` 候选，不虚构）。
> 每个任务映射到 `specs/spec.md` 的 CAP-xxx 能力号与 `design.md` 模块。验收以有权重方式列出可测项。
>
> **当前快照**：全系统大部分能力已落地（`spec.md` 状态表 implementation），故绝大多数 TASK 标 `[done]`；
> 未实现项集中在文末「候选 / backlog」(`[todo]`)。新改动按 `agreement.md` §2 走 change 流程，在对应 TASK 下挂后续。

---

## 1. 配置层（TASK-CONF-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-CONF-001 | [done] | 集中配置单例 + pydantic-settings | CAP-CONF-001 `config/settings.py` | `get_settings()` 全局唯一（lru_cache）；`SettingsConfigDict` 从 `.env` 加载、`extra=ignore`、`case_sensitive=False` |
| TASK-CONF-002 | [done] | 全量配置项分组、默认值完备 | CAP-CONF-002 `config/settings.py` | LLM/DB/安全/工具/SchemaLinking/HITL/记忆/裁剪/导出/Agent/API 各组不缺失；全部有默认值 |
| TASK-CONF-003 | [done] | 敏感值环境化、不硬编码 | CAP-CONF-003 | `api_key`/`db_password` 等经 `.env`；代码内无明文密钥 |
| TASK-CONF-004 | [done] | 上下文窗口推断 + 预算 | CAP-CONF-004 `context_budget` | `window×0.8`；`_infer_context_window` 按模型名回落 128k |
| TASK-CONF-005 | [done] | 用户同义词映射 | CAP-CONF-005 `user_synonym_map` | `schema_synonyms` 解析为 `{词:[表]}`，容错段格式 |

## 2. 数据库 / schema / schema linking（TASK-DB-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-DB-001 | [done] | 异步连接池与超时执行 | CAP-DB-001 `core/database/pool.py` | `fetch(sql, timeout)` 严格执行超时；连接池大小可配 |
| TASK-DB-002 | [done] | Schema 管理三件套 | CAP-DB-002 `core/database/schema.py` | list_tables / get_table_schema / get_sample_data 可用 |
| TASK-DB-003 | [done] | 相关表召回（schema linking） | CAP-DB-003 `schema_linking.py` | 相关性评分排序、上限 `schema_max_relevant_tables`、命中理由 |
| TASK-DB-004 | [done] | 低基数列样例抓取开关 | CAP-DB-004 | `schema_value_profiling` 开关生效 |
| TASK-DB-005 | [done] | 表/结构缓存有界 | CAP-DB-005 | 缓存带容量/TTL，不无界增长 |

## 3. SQL 安全（TASK-SEC-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-SEC-001 | [done] | SQL 多层校验 | CAP-SEC-001 `sql_validator.py` | AST / 关键字·危险函数黑名单 / 注入检测 / 多语句攻击均拦截 |
| TASK-SEC-002 | [done] | SQL 清理 + 自动 LIMIT | CAP-SEC-002 `sql_sanitizer.py` | 规范化、危险注释移除、LIMIT 钳制到 `sql_max_rows` |
| TASK-SEC-003 | [done] | 风险三态评估 | CAP-SEC-003 `risk_assessor.py` | CRITICAL→DENY / HIGH·MEDIUM→CONFIRM / LOW→ALLOW |
| TASK-SEC-004 | [done] | 敏感表识别 + 中文回述 | CAP-SEC-004 `sql_to_natural_language.py` | HITL 展示用自然语言描述命中表/风险 |
| TASK-SEC-005 | [done] | SQL 错误自纠 | CAP-SEC-005 `sql_error.py` | 13 类错误分类 + SQLSTATE + 修复建议，回喂 LLM 重试 |
| TASK-SEC-006 | [done] | 写操作默认不放行 | CAP-SEC-006 | `enable_sql_write=False` 时写 SQL 校验失败 |
| TASK-SEC-007 | [done] | 任意代码执行默认关 | CAP-SEC-007 `tools/__init__.py` | `create_custom_chart` 仅 `enable_custom_chart=True` 才进工具集 |

## 4. 工具层与权限边界（TASK-TOOL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-TOOL-001 | [done] | SQL 只读工具集 | CAP-TOOL-001 `sql_tools.py` | query_database / list_tables / get_table_schema / get_sample_data / get_relevant_schemas |
| TASK-TOOL-002 | [done] | 统一查询守卫 | CAP-TOOL-002 `boundaries.guard_query_sql` | 校验 + 系统表拒绝 + 表白名单 + LIMIT + 三态门禁 |
| TASK-TOOL-003 | [done] | 统一返回模型 | CAP-TOOL-003 `result_schemas.py` | `QueryResult` 等 Pydantic；`dump_result`/`parse_tool_result` 可用 |
| TASK-TOOL-004 | [done] | 声明式图表 | CAP-TOOL-004 `chart_tools.py` + `chart_spec.py` | 按 result_id 取数 → option_id；字段缺失精确报错、图型自动推荐 |
| TASK-TOOL-005 | [done] | 自定义绘图门控 | CAP-TOOL-005 | 线程池 + 沙箱兜住死循环，默认不暴露 |
| TASK-TOOL-006 | [done] | 分析 / 导出工具 | CAP-TOOL-006 `analysis_tools.py` | statistical_summary / data_profile / export_result（写文件需更高权限） |
| TASK-TOOL-007 | [done] | 长期记忆工具 | CAP-TOOL-007 `memory_tools.py` | remember / recall，由 `enable_memory_tools` 控制 |
| TASK-TOOL-008 | [done] | 工具级权限子集 | CAP-TOOL-008 `tools/__init__.py` | full / read_only / query_only；未知 scope 回退 full |
| TASK-TOOL-009 | [done] | 系统表黑名单同源 | CAP-TOOL-009 `boundaries.SYSTEM_TABLES` | 与 `schema.py` 同源一致；禁止查询 checkpoint/store 表 |

## 5. Agent 与中间件（TASK-AGENT-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-AGENT-001 | [done] | sync/async 双版本 agent | CAP-AGENT-001 `agent/` | 能力一致；async 用 AsyncPostgresSaver 持久化短期记忆 |
| TASK-AGENT-002 | [done] | 系统提示词工作流 | CAP-AGENT-002 `prompts.py` | 先 get_relevant_schemas 再执行；图表先查取 result_id；不臆造表/列；SQL 自纠 |
| TASK-AGENT-003 | [done] | 载荷裁剪中间件 | CAP-AGENT-003 | 跨轮压缩 ToolMessage（condense_tool_results） |
| TASK-AGENT-004 | [done] | 长上下文自动摘要 | CAP-AGENT-004 | token 预算触发（SummarizationMiddleware） |
| TASK-AGENT-005 | [done] | 瞬时错误自动重试 | CAP-AGENT-005 `middleware/config.py` | ToolRetryMiddleware + `sql_retry_on_transient` |
| TASK-AGENT-006 | [done] | 错误结构化格式化 | CAP-AGENT-006 | 工具异常封装为 ToolError，不裸 str(e) 回喂 |
| TASK-MID-001 | [done] | 本地日志中间件 | CAP-MID-001 | logging_middleware |
| TASK-MID-002 | [done] | HITL 中断配置 | CAP-MID-002 | query_database 需审核；只读工具自动放行 |
| TASK-MID-003 | [done] | Checkpointer 高可用 | CAP-MID-003 | AsyncPostgresSaver 优先，失败回退 InMemory |
| TASK-MID-004 | [done] | 长期记忆 Store 静默降级 | CAP-MID-004 | AsyncPostgresStore 失败降级（记忆为加分项） |

## 6. API 与前端（TASK-API-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-API-001 | [done] | 核心端点与契约 | CAP-API-001 `api/routes.py` | query/approve/state/export/chart/health/logs/stream/checkpoints 端点齐备；契约见 `api-spec.yaml` |
| TASK-API-002 | [done] | Bearer Token 鉴权 | CAP-API-002 `api/main.py` | `API_AUTH_TOKEN` 非空时全 `/api/**` 需鉴权；恒定时间比较 |
| TASK-API-003 | [done] | CORS 安全 | CAP-API-003 | `cors_origins` 读取；`*` 时禁 credentials |
| TASK-API-004 | [done] | Web 前端 | CAP-API-004 `static/index.html` | 查询交互 + 会话管理 + ECharts 矢量渲染 + HITL 审批界面 |
| TASK-API-005 | [done] | 查询结果提取 | CAP-API-005 | /query 返回最后成功结果的 columns/data/markdown |

## 7. Utils（TASK-UTIL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-UTIL-001 | [done] | 结果引用缓存有界 | CAP-UTIL-001 `utils/result_store.py` | 上限 50 条 / 10 分钟过期 |
| TASK-UTIL-002 | [done] | ECharts option 构建器 | CAP-UTIL-002 `utils/chart_spec.py` | dataset + encode；字段缺失精确报错 |
| TASK-UTIL-003 | [done] | 导出管理 | CAP-UTIL-003 `export_manager.py` | CSV/XLSX；`export_max_rows` 采样上限 |
| TASK-UTIL-004 | [done] | 图表沙箱 + checkpoint 清理 | CAP-UTIL-004 | 安全 globals 沙箱；checkpoint_cleanup 可用 |

## 8. 评测与测试（TASK-EVAL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-EVAL-001 | [done] | Text2SQL 回归评测 | CAP-EVAL-001 `eval/run_eval.py` | 跑 golden 用例 |
| TASK-EVAL-002 | [done] | Golden 集基线 | CAP-EVAL-002 `golden_queries.json` | 覆盖表检索/聚合/关联/写操作拒绝/结构检索 |
| TASK-EVAL-003 | [done] | 单元测试覆盖 | CAP-EVAL-003 `tests/` | 安全校验/工具边界/载荷裁剪/返回结构/SQL 错误/图表 spec（76 项） |
| TASK-EVAL-004 | [done] | 测试硬门槛 | CAP-EVAL-004 | `pytest tests/ -q` 全绿为改动门槛 |

---

## 候选 / backlog（`[todo]`，未实装）

> 对齐 `specs/spec.md` 状态表备注与 `agreement.md` 文末候选；**新改动先建 change 再挂到这里**。

| ID | 状态 | 候选任务 | 动机 | 落点建议 |
|----|------|----------|------|----------|
| TASK-BACKLOG-001 | [todo] | schema linking 改 Embedding 语义检索 | `get_relevant_schemas` 仍基于硬编码关键词映射，表多时召回不稳（agreement 候选） | `core/database/schema_linking.py` |
| TASK-BACKLOG-002 | [todo] | 同步版 agent 补消息裁剪中间件 | 与异步版对齐（agreement 候选） | `agent/` |
| TASK-BACKLOG-003 | [todo] | golden 集扩展召回/关联/安全边界 case | 现行用例较少，回归覆盖不足（spec 状态表备注） | `eval/golden_queries.json` |
| TASK-BACKLOG-004 | [done] | `export_result` 接入统一 SQL 守卫 | 未走 `guard_query_sql`，存在并行校验路径（proposal §3.3 已知隐患） | 已落地：`tools/analysis_tools.py` 改用 `guard_query_sql`；测试 `test_export_result_rejects_system_table_without_db` |

---

*版本：v0.1（依据 `specs/spec.md` 与既有 change 整理） | 更新：2026-10-13*
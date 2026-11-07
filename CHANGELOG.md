# Changelog

本文档记录本项目的所有重要变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的惯例。

## [Unreleased]

### 安全/检索/写操作/评测 四强化（注入加固 · 语义重排 · 写回看 · 语料扩集）

- **注入检测加固**（CAP-SEC-011）：`core/security/sql_validator.py` 在注入检测层补「恒真/恒假布尔注入」——仅当比较符**两侧都是字面量**（`数字=数字`、`'串'='串'`）时拒绝（`WHERE 1=1`、`OR 1=1`、`OR 'a'='b'`）；`region='Jingdong'`、`amount>100` 左是标识符不命中 → **不误杀**（`accept03/04` 控制组锁死）。收掉 `eval/badcases.md` 的恒真注入待办。
- **坏 case 自动沉淀**（CAP-EVAL-005）：`eval/mine_badcases.py` 新增 `--sink-security [--apply]`，把被安全/校验层拒绝的 `query_database` 失败调用按规范化 SQL 去重沉淀进 `security_deny.json`（默认 dry-run、幂等、跳过已存在）。
- **Embedding 语义重排**（CAP-DB-003 增强）：`core/database/schema_linking.py` 新增纯函数 `rerank_with_embeddings`，把「查询 × 表合成文本」相似度与关键词分加权重排；新增配置 `schema_embed_enabled`（默认关零行为变化）+ `schema_embed_fn`（可选 embedder 点分导入）；`SchemaManager.get_relevant_schemas` 启用时尝试加载、失败静默回退关键词。关键词仍打底，零新依赖。
- **写操作 RETURNING 回看 / VALUES 批量**（CAP-SEC-008 增强）：`tools/sql_tools.py` 写分派识别 `RETURNING`（走 `db_pool.fetch` 抓回写入行回显 `data/columns`，仍不入 result_store、写后仍清 schema 缓存）；多行 `VALUES (...),(...)` 即单条批量插入；docstring 提示 LLM。多语句事务**有意不做**（校验层拒堆叠语句是安全特性，非缺口）。
- **评测语料扩集**（CAP-EVAL-002）：`eval/cases/` 追加——schema_linking 11 例（多表关联 s07/s10/s11、列名/列注释驱动 s08/s09）、routing_guard 17 例（折线/饼图 r13/r14、结构 r15、清空恶意 r16、合法聚合 r17）、security_deny 13 例（恒真注入拒 sec06-09 + 放行控制 accept03/04）。
- `py -m pytest tests/ -q` **203 项全绿**（新增 `test_mine_badcases.py` / `test_write_returning.py` / `test_schema_embed.py` + `test_security.py` 增 7 例）；`py -m eval.run_eval` **41/41 不回归**。change 归档 `openspec/archived/{injection-defense-hardening,write-operations-enhanced,embedding-schema-retrieval,eval-corpus-expansion}/`。

### dsh 思想迁移四改动（准入门 · 单一写者 · 少设置 · 效果队列）

迁移 deepseek 开源超级智能体（`dsh-superagent` / `deepseek-harness`）的哲学与架构到本项目：

- **请求准入门 + 注意力经济**（CAP-SEC-010）：`core/security/admission.py` 新增 `AdmissionGate`，在 `/query` 入口合成「来源 × 意图」确定性准入（admit/deny/clarify/reply）。allowlist 模式校验 `X-Admission-Key`；寒暄/结构询问等低信号安全意图用固定文案直答、**不烧 LLM token**（注意力经济，文案经 `intent_canonical_replies` 配置）。`enable_admission_gate`（默认关）门控，接通不改变现状。测试 `tests/test_admission.py`（14 例）。change 归档 `openspec/archived/admission-gate-attention/`。
- **单一写者纪律**（CAP-UTIL-006）：`utils/bounded_cache.py` 新增 `BoundedTTLCache` 有界 TTL 缓存原语，收敛 `result_store` 与图表 spec 缓存的手写重复实现；修复图表读路径摧毁式 `.pop()` → 只读 `get`（「读不写」）；`docs/state-owners.md` 记录各状态唯一写者。测试 `tests/test_bounded_cache.py` + `tests/test_single_writer.py`。change 归档 `openspec/archived/single-writer-discipline/`。
- **少设置审计**：按 dsh「一个默认值能覆盖就删 setting」删除 `db_max_overflow` / `cache_ttl` / `redis_url` / `agent_verbose` 四个无消费方配置；缓存 TTL 归 `BoundedTTLCache` 常量单一来源。change 归档 `openspec/archived/few-settings-audit/`。
- **持久化效果队列 + 指数退避**（CAP-UTIL-007）：`utils/effect_queue.py` 新增 `AsyncEffectQueue`（key 幂等入队、指数退避 + 抖动、可选 JSONL 持久化、pending/settled/failed 健康计数）；`run_sql_durable` 接通 SQL 瞬时错误退避层（`effect_queue_max_retries` 默认 2）。测试 `tests/test_effect_queue.py`。change 归档 `openspec/archived/durable-effect-queue/`。
- `py -m pytest tests/ -q` **174 项全绿**；`py -m eval.run_eval` 不回归。

### 模型视图可重建不变量（M1，可观测：日志 ⟹ 模型视图可重建）

- **确定性重建函数**（`core/recon.py`，纯函数、无 DB/LLM）：`reconstruct_model_messages(events)` 把「会话事件序列」编排成 LangChain 消息列表（system / user / assistant_tool_calls / tool_result / resume / summary），tool_result 经 `tool_call_id` 与 AIMessage 配对；未知事件类型 fail loud。`session_events_from_tool_records` 把工具日志记录转成可重建事件，保序（append-only）。
- **忠实捕获**（`middleware/logging_wrapper.py`）：工具调用日志从硬编码 `thread_id='current'` 修正为真实会话 id（解析自 `request.runtime.config.configurable.thread_id`，缺失回退）；新增 `model_view` 字段，用与送入 LLM 相同的 condense 阈值（`config.settings.tool_result_max_*`）对结果裁剪后落盘，使「日志记录的内容」==「模型实际看到的内容」（Model-visible ⟺ logged）。受 `recon_model_view_enabled`（默认 True）门控。
- **新增测试**：`tests/test_recon.py`（10 例：轮序、多步配对、忠实性、HITL resume、summary、未知事件 fail loud、records→events 保序等，全 DB/LLM-free）。`pytest tests/ -q` 138 项全绿；`py -m eval.run_eval` 25/25 不回归。
- **文档回填**：`spec.md` 新增 `CAP-RECON-001/002`、状态表补 recon 行；`tasks.md` 新增 `TASK-RECON-001`；`README.md` 日志特性与配置表补 `recon_model_view_enabled`。change 见 `openspec/archived/recon-model-view-invariant/`。

### 意图路由器接线 /query（前置拒答，省 LLM 成本）

- **`intent_guard` 接线 `/query`**（TASK-BACKLOG-004 落地）：`core/security/intent_guard.py` 新增纯函数 `maybe_short_circuit(text) -> Optional[str]`，仅当 `ENABLE_INTENT_ROUTER=True` 且意图判定为明确 deny（恶意/寒暄/离题）时返回短路文案；`api/routes.py` `/query` 在进 Agent/LLM 前调用，命中即返回 `success=False` + 文案。默认关 → 零行为变化；只拒 `deny`、不拒歧义（保守低误杀）。
- **新增测试**：`tests/test_intent_router_wiring.py`（7 例，覆盖开关开/关 + 恶意/寒暄/离题/合法查询/歧义/空索引兜底，不连 DB/LLM）。`pytest tests/ -q` 128 项全绿；`py -m eval.run_eval` 25/25 不回归。
- **文档回填与防漂移**：`spec.md` CAP-SEC-009 / 状态表、`tasks.md` B004 → 已落地、`terminology.md` TERM-014、`README.md` 配置表与安全设计；同步清理 `README` 架构图里已删的 `viz_tools.py`、`design.md` §5 指向已归档 change 的 stale 引用、`tasks.md`/`spec.md` 中实际已实现的 B002。change 见 `openspec/archived/intent-router-wiring/`。

### SDD 开发规范完善（一致性 + 关键流程 + 优化路线）

- **修规范文档 stale 到代码基线**：`openspec/specs/spec.md` / `tasks.md` / `terminology.md` / `proposal.md` / `design.md` 中已删除的 `eval/golden_queries.json` 迁移为 `eval/cases/`（schema_linking / security_deny / routing_guard）；测试数由写死 76 改为当前 `tests/` 121 项（注明以运行时为准）。
- **补新能力 CAP/TASK/TERM**：`spec.md` 新增 `CAP-SEC-008 写操作受边界保护`、`CAP-SEC-009 意图路由器 intent_guard`、`CAP-API-006 /api/stats`、`CAP-API-007 checkpoint 维护端点`、`CAP-UTIL-005 bench.loadtest`；`tasks.md` 对应补 `TASK-SEC-008/009`、`TASK-API-006/007`、`TASK-UTIL-005`；`terminology.md` 新增 `TERM-014 意图路由器`、`TERM-015 写操作边界`。
- **规范流程补关键约束**：`openspec/agreement.md` 新增 `§2.5 Definition of Done`（合入前 5 条 checklist）、`§6 Keep Docs in Sync`（归档时回填 CAP/TASK/TERM、单一来源、发现 stale 立即修）、`§5 Avoid#7`（不让治理文档漂移 / 各写一套）。
- **后续优化方向扩为带优先级路线**：`openspec/tasks.md` backlog 由 3 项扩到 10 项（B001..B010），每项含【优先级 P0-P2 / 成本 / 收益 / 关联 CAP / 落点】，覆盖 Embedding schema 检索、意图路由器接线 `/query`、LLM 提示词缓存、多 worker + Redis、可观测 metrics/追踪、写操作 RETURNING 增强、更严注入检测 + 坏 case 自动扩集、RBAC 与速率限制等。
- 纯治理文档改动，无代码/API/配置变更；`pytest tests/ -q` 121 项全绿。change 见 `openspec/archived/sdd-conventions-polish/`。

### 写操作支持（INSERT / UPDATE / DELETE，受边界保护）

- **`query_database` 支持增删改写操作**（`tools/sql_tools.py`）：`guard_query_sql` 通过后按 DML 分派——写操作走 `db_pool.execute`、解析受影响行数（asyncpg tag 尾部整数）返回 `QueryResult(row_count=受影响行数, data=[{操作, 受影响行数}])`；`await schema_manager.clear_cache()` 写后失效 schema 缓存刷新 stale 行数/样本；写结果**不入 `result_store`**（写结果不适合作图表数据源）。SELECT 路径（`db_pool.fetch` + `set_result`）不变。
- **修 risk_assessor INSERT 误杀**（`core/security/risk_assessor.py`）：原「写操作无 WHERE → NO_WHERE_CLAUSE → CRITICAL → DENY」会把 `INSERT`（本就不该有 WHERE）一并拒掉，「添加数据」永远不可用。现判定限定为 UPDATE / DELETE；INSERT 判 HIGH→CONFIRM（进人工审核），DELETE/UPDATE 无 WHERE 仍 CRITICAL→DENY 立即拒绝，安全基线不降。
- **写操作默认仍关**：复用既有 `ENABLE_SQL_WRITE`（默认 `false`）放行写校验；写操作天然走 HITL（`query_database` 在 `tools_requiring_approval`）强制人工 approve/reject。双保险（DENY 门禁 + 人审）。
- **提示词写操作边界**（`agent/prompts.py`）：新增写操作小节——INSERT 用显式列名 `VALUES`；DELETE/UPDATE 必须带 WHERE 限定范围；写会触发人审、完成后回述受影响行数；不硬编码示例表名。
- **新增测试**：`tests/test_risk_assessor.py`（INSERT 无 WHERE 不 DENY / DELETE·UPDATE 无 WHERE 仍 DENY / 带 WHERE 写 CONFIRM）、`tests/test_sql_tools_write.py`（写分派返回行数、清 schema 缓存、不入 result_store、SELECT 路径不受影响）。`pytest tests/ -q` 121 项全绿。

### 并发压测与并发能力提升

- **新增压测工具 `bench.loadtest`**（`bench/loadtest.py`，`py -m bench.loadtest`）：httpx+asyncio 并发压测，可压轻量端点 `/health`/`/api/stats`（框架吞吐基线）或真实 `/query` 全链路（调 LLM+DB）。支持 `--endpoint/--concurrency/--duration|--requests/--query|--query-file`、`--thread-mode {unique,reuse,per-worker}`、Bearer 鉴权、进度打印、`--json`；`endpoint=query` 内置费用/耗时警告，`--dry-run` 只打印计划不发包。
- **新增 `/api/stats` 只读端点**：返回连接池（size/min/max/idle）、线程池配置、结果缓存条目数，供压测闭环调参。
- **连接池/线程池去硬编码**：`core/database/pool.py` `min_size=5` 改为读 `DB_POOL_MIN_SIZE`；三处 `ThreadPoolExecutor(max_workers=2)`（`tools/analysis_tools.py`、`tools/chart_tools.py`、`utils/chart_sandbox.py`）统一读 `TOOL_THREAD_POOL_SIZE`（默认 4）。`DB_POOL_SIZE` 默认 10→20（`SQL_TIMEOUT=30` 下慢查询占连接更久，池满 acquire 排队天然节流）。
- **`DB_MAX_OVERFLOW` 标废弃**：asyncpg 无 overflow 概念（原字段未实现），保留字段避免 `.env` 同名变量被 `extra="ignore"` 静默吞掉，默认置 0。
- **修复 agent 缓存并发冷启动真洞**：`agent/analyst_agent.py` 异步版 `get_cached_async_agent` 用 futurization（pending task 去重），高并发首请求不再重复 `create_async_agent`；失败清 pending 防悬挂；同步版加 `threading.Lock`。
- **结果缓存加并发说明注释**（`utils/result_store.py`、`tools/chart_tools.py`）：单事件循环无真争用故不加锁；若序列化进线程池改 `threading.Lock`，多 worker 共享改 Redis。
- **uvicorn 调参**：`API_BACKLOG=2048`、`API_KEEPALIVE=5`、`API_GRACEFUL_SHUTDOWN=30`，`run_server.py` 与 `api/main.py` 透传（适配 uvicorn 0.52 的 `timeout_keep_alive`/`timeout_graceful_shutdown`）；默认仍单 worker。
- **新增测试**：`tests/test_settings_defaults.py`、`tests/test_agent_cache_concurrency.py`、`tests/test_loadtest_cli.py`。`pytest tests/ -q` 109 项全绿。
- 说明：本机 Postgres 未运行，真实 `/query` 压测冒烟暂缓（需 DB 可达后执行）。

### 重构（安全收敛）—— export_result 接入统一 SQL 守卫

- **消除导出并行校验路径**：`tools/analysis_tools.py` 的 `export_result` 弃用内联 `sql_validator.validate` + `sql_sanitizer.sanitize`，改与 `query_database` 同走 `tools.boundaries.guard_query_sql`。导出从此具备系统表白名单校验、风险三态 DENY 门禁、统一错误语义（对齐 agreement Avoid#4「不造重复实现」）。
- **新增测试**：`tests/test_tool_boundaries.py` 追加 `test_export_result_rejects_system_table_without_db`（导出系统表被拒且未触库）。`pytest tests/ -q` 99 项全绿。
- 架构备注：`guard_query_sql` 对校验失败 / 系统表拒绝 / DENY 三种情况统一返回 `(None, error)`，故导出统一走 `if guard_err` 分支即可覆盖；文件格式、下载接口与返回结构均未变。

### 确定性回归评测（坏 case / 错误案例 / 评测集）

- **新增确定性意图路由器** `core/security/intent_guard.py`：把用户 NL 分类成 `query/chart/info/malicious/smalltalk/ambiguous/out_of_scope`，返回 `IntentVerdict`（含 deny/clarify 语义），用纯逻辑复用 `rank_relevant_tables` 判实体命中；NL 层「拒答 / 澄清 / 报错」从此有可单测、可进 CI 的确定性入口。
- **评测集重构**：`eval/run_eval.py` 从单场景 5 条改为多场景聚合 harness；语料迁至 `eval/cases/` 三文件（`schema_linking` / `security_deny` / `routing_guard`）；删除了从未被校验的死字段 `sql_contains` 与旧的 `golden_queries.json`。
- **评测索引贴近生产**：合成索引补上了同义词表（`build_synonym_map()`），修正旧索引「今年订单总数」等核心业务词不命中的假评测。
- **文档与工具**：新增 `eval/badcases.md`（坏 case 台账 + 已知盲点，含恒真注入 `OR '1'='1'` 在 SQL 层不拦的待办）、`eval/mine_badcases.py`（扫 `logs/tool_calls.jsonl` dump 失败调用）。
- **新增测试**：`tests/test_intent_guard.py`、`tests/test_eval_regression.py`；重写 `tests/test_eval_text2sql.py`。`pytest tests/ -q` 92 项全绿。
- **配置**：`ENABLE_INTENT_ROUTER`（默认 `false`，接线 `/query` 的开关，当前仅评测直接调用路由器，不改运行时行为）。

### 修复（P0）—— 瞬时错误重试链路 + schema 缓存时效

- **移除坏的 `ToolErrorMiddleware`**：`middleware/config.py` 中 `ToolErrorMiddleware()` 无参构造即抛 `ValueError`（该版本要求必传 `on_error`/`aon_error`），导致 `get_middleware_list()`/`create_agent()` 直接失败、重试中间件从未被构建；且其职责与 `ToolRetryMiddleware` 的 `on_failure="continue"` + `query_database` 自纠重叠，按 Avoid#4 移除。
- **瞬时错误真正进入重试链路**：`tools/sql_tools.py` 的 `query_database` 原先用 `except Exception` 吞掉所有异常转 `success=false`，使 `ToolRetryMiddleware.retry_on=is_transient_error` 永远等不到瞬时异常。现改为瞬时错误（连接中断/死锁/超时等）直接 `raise` 交给中间件重试，逻辑错误仍转结构化失败回喂 LLM 自纠。
- **修复 schema 缓存跨天失效**：`core/database/schema.py` 缓存 TTL 判断用 `timedelta.seconds`（`[0,86400)` 模）会跨天回绕为「永远新鲜」，改 `total_seconds()` 正确判过期。
- **新增测试**：`tests/test_sql_tools.py`（瞬时分流）、`tests/test_schema_cache.py`（TTL 过期/命中）、`tests/test_tool_boundaries.py` 追加中间件构建用例。`pytest tests/ -q` 98 项全绿。

## [1.3.0] - 2026-10-03

### 图表生成（声明式 ECharts + 数据引用化）

- **数据引用化，降低 token 消耗**
  - 新增 `utils/result_store.py`：有界 TTL 缓存（上限 50 条、10 分钟过期，模式复用既有图表缓存）存储查询结果。
  - `tools/sql_tools.py`：`query_database` 成功时把 `columns+rows` 存入 result_store，`QueryResult` 新增 `result_id`。
  - `tools/chart_tools.py`：`create_chart` 签名改为 `(result_id, chart_type, x_field, y_field, title)`，服务端按 result_id 取数，工具入参从「重传完整结果（数百 token）」降至「约 20 token 的固定 spec」，且消除 `data[:100]` 截断导致的丢数据。
  - `agent/prompts.py`：图表规则改为「先查查询再传 result_id」，不再让 LLM 把数据重传进工具参数。

- **声明式 ECharts，提高精度**
  - 新增 `utils/chart_spec.py`：`build_echarts_option()` 把结果构建为紧凑 ECharts option（内嵌 dataset + encode）；字段缺失时返回精确错误并列出合法字段，驱动 LLM 精准重试；`chart_type=None` 时按列基数/数值性自动推荐图型。
  - `tools/chart_tools.py`：默认图表改为返回 `option_id` 句柄，前端经 `GET /api/chart/option/{id}` 取 option 渲染，弃用 matplotlib→80dpi PNG 的默认路径；`create_custom_chart`（PNG）保留。
  - `api/routes.py`：新增 `GET /api/chart/option/{chart_id}`；`extract_chart_data` / `extract_all_chart_data` 同时识别 `option_id`。
  - `static/index.html`：引入 ECharts CDN，`showChart` / `showCharts` 改为 fetch option 后 `echarts.setOption` 矢量渲染，PNG 走 `<img>` 回退。

- **返回模型**
  - `tools/result_schemas.py`：`QueryResult` 新增 `result_id`；`ChartResult` 新增 `option_id`（保留 `image_base64` 兼容）。`RESULT_KEEP_FIELDS` 由模型字段自动派生，裁剪中间件无需改动。

- **新增测试**：`tests/test_chart_spec.py` 8 个用例（四种图型 option 结构、字段缺失精确报错、自动图型推荐等）。`pytest tests/ -q` 76 项全过。

## [1.2.0] - 2026-09-04

### SQL 可靠性（自纠增强）

- **结构化 SQL 错误自纠**
  - 新增 `core/security/sql_error.py`：`classify_sql_error()` 把常见 PostgreSQL 错误（列/表不存在、列歧义、函数不存在、语法错误、除零、超时、GROUP BY/聚合、权限、类型不匹配等 13 类）分类成 `{code, summary, suggestion}`，`build_self_correction_message()` 拼装面向 LLM 的自纠反馈。
  - `tools/sql_tools.py`：`query_database` 执行失败时不再只回传裸报错字符串，改为输出「[错误码] + 原始错误 + 修复建议」，驱动 generate→execute→reflect 重试。
  - `agent/prompts.py`：新增「SQL 自纠与反思」规则，指导 LLM 读到修复建议后先用 get_table_schema/get_relevant_schemas 核对真实结构再纠正重试、不臆造表名/列名、重试上限 3 次后如实报告。

### 结果展示

- **查询结果 Markdown 表格**
  - `tools/result_schemas.py`：`QueryResult` 新增 `to_markdown()`，把 columns+data 转成 GitHub 风格管道表格（单元格转义 | 与换行、超长截断）。
  - `api/routes.py`：`/api/query` 成功时新增 `extract_query_result()`，把最后一个成功查询的 `data` 与 `markdown` 回传（补齐此前这些字段一直为空的缺口）。
  - `api/schemas.py`：`QueryResponse` 新增 `markdown` 字段。
  - `static/index.html`：结果区新增管道表格→HTML 渲染，查询结果以表格形式展示。

### 工程化

- **新增单元测试**：`tests/test_sql_error.py`（分类 10+ 分支）、`tests/test_result_schemas.py` 增加 `to_markdown` 5 个用例。`pytest tests/ -q` 全通过。

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
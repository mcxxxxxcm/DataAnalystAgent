# Data Analyst Agent · 智能数据分析助手

一个 **Text2SQL 架构** 的自然语言数据分析助手。用户用中文提问，Agent 自动完成「理解意图 → 检索表结构 → 生成并校验 SQL → 执行查询 → 展示结果/图表」的完整闭环，同时内置 **人工审核（Human-in-the-Loop）**、**SQL 多层安全校验** 与 **多轮对话短期记忆**。

技术栈：`LangChain / LangGraph (Deep Agents)` + `FastAPI` + `PostgreSQL/asyncpg`。

---

## 目录

- [核心特性](#核心特性)
- [项目架构](#项目架构)
- [Quick Start](#quick-start)
- [配置说明](#配置说明)
- [API 接口](#api-接口)
- [安全设计](#安全设计)
- [前端界面](#前端界面)
- [已知问题 / 改进方向](#已知问题--改进方向)

---

## 核心特性

| 能力 | 说明 |
|------|------|
| 🧠 自然语言转 SQL | Agent 根据用户查询自动检索相关表结构并生成 SQL |
| 🔒 多层 SQL 安全校验 | AST 解析 + 关键字/危险函数黑名单 + 注入检测 + 自动注入 LIMIT |
| 👤 人工审核 (HITL) | 写操作 / 高风险查询在执行前拦截，由人工 approve/reject |
| 🧵 多轮对话短期记忆 | 基于 `AsyncPostgresSaver`，会话（thread_id）上下文持久化到 PostgreSQL |
| 📊 自动图表 | `create_chart` 生成柱状图/折线图/饼图/散点图，图片 base64 返回前端 |
| 📝 本地结构化日志 | 全部工具调用落盘为 JSONL，敏感字段自动脱敏，支持日志轮转 |
| 🖥️ 内置 Web 界面 | `static/index.html` 提供对话式前端 |

---

## 项目架构

```
配置层          config/settings.py          pydantic-settings 配置（LLM/DB/安全/Agent）
─────────────────────────────────────────────────────────────────────────
核心基础设施层   core/                       不暴露给 LLM 的内部能力
   ├─ database/ │ pool.py  asyncpg 连接池单例
   │            └ schema.py  表结构缓存 + LLM 友好格式 + 关键词→表映射
   └─ security/ │ sql_validator.py  8 层 SQL 校验（AST/黑名单/注入）
                │ sql_sanitizer.py  清理 + 自动 LIMIT + 复杂评估
                └ risk_assessor.py  风险评级 → 是否需人工审核
─────────────────────────────────────────────────────────────────────────
工具层          tools/                      暴露给 LLM 的可调用工具
   ├─ sql_tools.py     query_database / list_tables / get_table_schema /
   │                   get_sample_data / get_relevant_schemas
   ├─ chart_tools.py   create_chart / create_custom_chart（chart_id 缓存）
   └─ viz_tools.py     旧的独立图表工具（create_*_chart，当前未纳入 ALL_TOOLS）
─────────────────────────────────────────────────────────────────────────
Agent 层        agent/                      基于 create_agent (Deep Agents) 组装
   ├─ analyst_agent.py  工厂：同步(内存)/异步(Postgres) 两种 Agent
   └─ prompts.py        系统提示词 + Few-shot + 提示词构建函数
─────────────────────────────────────────────────────────────────────────
中间件层        middleware/                  LangChain 官方中间件 + 本地日志
   ├─ config.py         HITL 配置 / checkpointer(AsyncPostgresSaver) 初始化
   ├─ logging_wrapper.py 工具调用日志中间件（@wrap_tool_call）
   └─ logging_middleware.py  本地日志记录器（脱敏/轮转/JSONL）
─────────────────────────────────────────────────────────────────────────
API 层          api/                         FastAPI 应用与路由
   ├─ main.py           应用生命周期 + CORS + 静态资源托管
   ├─ routes.py         /query /approve /stream /health /logs /checkpoints/*
   └─ schemas.py        Pydantic 请求/响应模型
─────────────────────────────────────────────────────────────────────────
工具函数层      utils/                       chart_sandbox(代码执行沙箱) / checkpoint_cleanup
前端            static/index.html           对话式 Web UI
入口            main.py / run_server.py / start_windows.py
```

### 一次查询的调用链

```
用户提问
  └─ POST /api/query  (api/routes.py)
       └─ agent.ainvoke  (agent/analyst_agent.py)
            ├─ 系统提示词 (agent/prompts.py)
            ├─ 中间件: 日志 / 消息裁剪 / HITL
            └─ LLM 依次调用工具 (tools/)
                 ├─ get_relevant_schemas → core/database/schema.py → PostgreSQL
                 ├─ query_database          → core/database/pool.py → PostgreSQL
                 │      └─ 安全校验由 middleware/ 侧 HITL + core/security 保障
                 └─ create_chart            → utils/chart_sandbox.py → 图片 base64
                                     │              └ 命中 HITL → 返回 requires_approval，等待 /api/approve
                                     └─ API 提取图表数据返回前端
```

### 设计要点

- **基础设施与工具分层隔离**：`core/` 中的数据库连接、Schema、安全校验均不暴露给 LLM；LLM 只能通过 `tools/` 接口间接访问。避免 LLM 拿到 `/etc/...` 等系统访问能力。
- **双 Agent 形态**：`create_agent()`（同步，内存 checkpointer，适合开发）与 `create_async_agent()`（异步，PostgreSQL 持久化 short-term memory，适合生产）。API 路由统一走异步版本。
- **短期记忆**：相同 `thread_id` 保持多轮上下文；`AsyncPostgresSaver` 持久化，服务重启不丢，同时提供 checkpoint 清理工具防止存储膨胀。
- **人工审核**：`query_database`（尤其写操作）在执行前触发 HITL 中断，前端拿到 `requires_approval` 后调用 `/approve` 放行或拒绝。

---

## Quick Start

前置依赖：Python 3.10+，运行中的 PostgreSQL，以及一个 OpenAI 兼容的 LLM API。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制 .env.example 或直接编辑 .env）
#    LLM: 兼容智谱 GLM / OpenAI 等
#    DB:  指定你的 PostgreSQL 连接信息

# 3. Windows 启动（处理 asyncio 事件循环策略）
python start_windows.py
# 或
python main.py
# 或直接 uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8085
```

启动后访问：

- 对话界面：`http://127.0.0.1:8085/`
- API 文档（Swagger）：`http://127.0.0.1:8085/docs`
- 健康检查：`http://127.0.0.1:8085/api/health`

> 首次启动会连接数据库并初始化 short-term memory 所需的 checkpoint 表。

---

## 配置说明

配置由 `config/settings.py`（pydantic-settings）管理，可通过 `.env` 或环境变量覆盖。

### LLM

| 变量 | 默认 | 说明 |
|------|------|------|
| `API_KEY` | 必填 | LLM API Key |
| `BASE_URL` | - | 兼容 OpenAI 协议的基础 URL（如 `https://open.bigmodel.cn/api/paas/v4`） |
| `LLM_MODEL` | `gpt-4-turbo` | 模型名（如智谱 `glm-4`） |
| `LLM_TEMPERATURE` | `0.0` | 温度，越低越确定 |
| `LLM_MAX_TOKENS` | `4096` | 最大生成 token |

### 数据库

| 变量 | 默认 | 说明 |
|------|------|------|
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` | 连接地址 |
| `DB_NAME` | `analytics` | 库名 |
| `DB_USER` / `DB_PASSWORD` | `postgres` / - | 账号密码 |
| `DB_POOL_SIZE` | `10` | 连接池大小 |
| `DB_MAX_OVERFLOW` | `20` | 最大溢出连接 |

### 安全

| 变量 | 默认 | 说明 |
|------|------|------|
| `SQL_MAX_ROWS` | `10000` | 查询最大返回行数（自动注入 LIMIT） |
| `SQL_TIMEOUT` | `30` | SQL 执行超时（秒） |
| `ENABLE_SQL_WRITE` | `false` | 是否允许 INSERT/UPDATE/DELETE |

### Agent / API

| 变量 | 默认 | 说明 |
|------|------|------|
| `MAX_RETRY_ATTEMPTS` | `3` | SQL 失败重试次数 |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8080` | 服务监听 |
| `API_RELOAD` | `false` | uvicorn 热重载，仅开发建议开启 |
| `API_AUTH_TOKEN` | 空 | 可选 Bearer Token 鉴权；留空不鉴权，生产建议设置 |
| `CORS_ORIGINS` | `*` | 允许的跨域来源，逗号分隔；配置具体来源时自动附带凭据 |
| `ENABLE_CUSTOM_CHART` | `false` | 是否启用 `create_custom_chart`（任意代码执行，风险高，默认关闭） |
| `REDIS_URL` | - | 可选，预留 Schema/结果缓存 |
| `CACHE_TTL` | `3600` | 缓存过期时间 |

---

## API 接口

所有接口挂载在 `/api` 前缀下，完整定义见 `api/schemas.py`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/query` | 提交自然语言查询，返回结果（或 `requires_approval` 待审核） |
| POST | `/api/approve` | 人工审核：`approve` / `reject` |
| GET | `/api/stream/{thread_id}?query=` | SSE 流式执行过程 |
| GET | `/api/state/{thread_id}` | 查看会话状态（含短期记忆历史） |
| GET | `/api/health` | 健康检查（含数据库连通性） |
| GET | `/api/logs` | 查询工具调用日志 |
| GET | `/api/checkpoints/stats` | checkpoint 存储统计 |
| POST | `/api/checkpoints/cleanup` | 清理过期 checkpoint（dry_run 默认开启） |
| POST | `/api/checkpoints/cleanup-orphaned` | 清理孤立 checkpoint |

### POST /api/query 示例

```bash
curl -X POST http://127.0.0.1:8085/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "查询各地区销售总额"}'
```

响应：带 `thread_id`（多轮对话复用）；若命中 HITL，返回 `requires_approval=true` 与 `approval_request`（含待审核 SQL、风险等级）。

### POST /api/approve 示例

```bash
curl -X POST http://127.0.0.1:8085/api/approve \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "...", "decision": "approve"}'
```

---

## 安全设计

本项目在「LLM 生成 SQL → 执行」路径上建立了多层防御：

1. **AST 层校验**（`sql_validator.py`）：用 `sqlparse` 解析语法树判断 DML 类型，只允许白名单操作（默认仅 `SELECT`）。
2. **黑名单检测**：禁止 `DROP / TRUNCATE / ALTER / CREATE / GRANT / REVOKE / EXEC`。
3. **危险函数黑名单**：禁止 `load_file / pg_read_file / copy / lo_import` 等高风险函数。
4. **注入检测**：识别 `--`/`/* */` 注释攻击、多语句拼接等模式。
5. **自动 LIMIT**（`sql_sanitizer.py`）：对无 LIMIT 的 SELECT 自动注入 `LIMIT max_rows`，防止全表扫描与内存溢出。
6. **风险评估**（`risk_assessor.py`）：结合复杂度、多表、写操作、无 WHERE、敏感表等维度评级，决定是否触发人工审核。
7. **人工审核 (HITL)**：写操作 / 高风险查询执行前中断，业务侧人工放行。
8. **日志脱敏**：工具调用中的密码、密钥等自动替换为 `***REDACTED***`。

---

## 前端界面

`static/index.html` 为单文件对话式 Web UI（内联 CSS/JS，无构建依赖），支持：

- 聊天式输入与结果展示
- 查询结果表格化呈现
- 图表图片展示
- 高风险操作的人工审核弹窗（approve / reject）

---

## 已知问题 / 改进方向

> 详细、分优先级的改进方案见 `CHANGELOG.md`。以下是截至当前版本的处理状态：

| # | 问题 | 状态 |
|---|------|------|
| 1 | API 无鉴权 | ✅ 已支持可选 Bearer Token（`API_AUTH_TOKEN`） |
| 2 | CORS `[*]` + credentials 组合风险 | ✅ 已改为可配置来源（`CORS_ORIGINS`），通配符时自动禁用凭据 |
| 3 | 沙箱 timeout 未生效 / 自定义代码执行风险 | ✅ 已真正实施超时；`create_custom_chart` 默认关闭 |
| 4 | `get_relevant_schemas` 靠硬编码关键词 | ⏳ 待做：建议改为基于 Embedding 语义检索 |
| 5 | 系统提示词写死示例表，与真实 Schema 脱节 | ✅ 已移除硬编码示例表，改为动态依赖 `get_relevant_schemas` |
| 6 | `chart_tools` 与 `viz_tools` 重复实现 | ✅ 已删除 `viz_tools.py`，收敛为单一实现 |
| 7 | 缺少测试 | ✅ 已为 `core/security` 增加单元测试（`tests/test_security.py`） |

---

## License / 说明

本项目为 Text2SQL 数据分析方向的示例实现，请结合实际生产环境进行安全加固后再上线。

---

*更多实现细节与持续维护说明，可阅读 `config/`、`core/`、`agent/`、`api/` 各模块顶部的模块注释。*
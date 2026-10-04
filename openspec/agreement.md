# OpenSpec Agreement

> **本文件是项目的「宪法」**。任何 AI Agent / 协作者在改动本仓库前必须先读这里。
> 英文为结构性关键词，中文为完整说明。本文件会持续演进，普通约定放正文，**已踩过的坑放文末 Avoid 小节**。

---

## 0. What is this project（项目是什么）

一个 **Text2SQL 架构** 的自然语言数据分析 Agent：用户中文提问，Agent 完成「理解意图 → 检索表结构 → 生成并校验 SQL → 执行 → 展示结果/图表」闭环，内置人工审核（HITL）、SQL 多层安全校验、多轮对话短期记忆。

## 1. Tech Stack & Architecture（技术栈与分层）

- 栈：`Python` + `LangChain / LangGraph (deepagents)` + `FastAPI` + `PostgreSQL/asyncpg`。
- **分层铁律**（改动时不要越层）：
  - `config/` 配置层 —— pydantic-settings，LLM/DB/安全/Agent 配置。
  - `core/` 核心基础设施 —— **不暴露给 LLM** 的内部能力（db 连接池、schema、security）。
  - `tools/` 工具层 —— 暴露给 LLM 的可调用工具（AI 能力边界在此，见 §3）。
  - `agent/` —— 创建 agent、系统提示词（prompts）。
  - `api/` + `static/` —— FastAPI 后端 + 前端。
  - `middleware/` / `utils/` / `eval/` / `tests/` —— 中间件 / 工具 / 评测 / 测试。

## 2. Change Workflow（改动工作流）

**除非改动属 trivial（一行修复、重命名、纯注释），否则必须先走 OpenSpec change 流程：**

1. 在 `openspec/changes/<slug>/` 新建一个 change，含三份文件：
   - `overview.md` —— **310 条**:一句话讲清 why / what / how。讲不清就不要动手。
   - `proposal.md` —— 具体方案：改动哪些文件、touch 哪些模块、取舍与风险。
   - `recipe.md` —— **给 LLM 的逐步执行剧本**：每一步含 `Context(为什么)` + `Action(做什么)` + `Validation(怎么验证)`。
2. 按 `recipe.md` 逐步执行，每步过验证点。
3. 改动带上对应测试，跑 `pytest tests/ -q` 全绿。
4. 合入前确认 `overview.md` 的「how」承诺都已兑现，把 change 目录移出 `changes/`（归档或删除）。

> template 见 `openspec/changes/_TEMPLATE/`。复制它生成新 change。

## 3. Safety Red Lines（安全红线，不可妥协）

- **SQL 一切工具调用**必须经过 `core/security` 的多层校验（AST / 关键字与危险函数黑名单 / 注入检测 / 自动 LIMIT）与 `RiskAssessor` 风险评级。
- **写操作 / 高风险查询**执行前必须进入 HITL，由人工 approve/reject。
- **任意代码执行默认关闭**：`create_custom_chart` 仅当 `.env` 显式 `ENABLE_CUSTOM_CHART=true` 才暴露进工具集。新增工具默认 `read-only`。
- **工具边界**：暴露给 LLM 的每个工具都要评估权限边界，新工具参考 `tools/boundaries.py` 现有约定。
- 引入新依赖 / 新工具 / 放宽权限前，先在 `proposal.md` 写清风险。
- 安全相关改动必须新增/更新测试（参考 `tests/test_security.py` / `test_tool_boundaries.py`）。

## 4. Engineering Standards（工程标准）

- 改动必须带测试；提交前 `pytest tests/ -q` 全绿。
- 文档语言：**代码注释用中文**；`openspec/` 内 change 文档**中英混合**（关键词英文，说明中文）。
- 用户可见变更更新 `README.md`；值得记录的历史变更追加 `CHANGELOG.md`（遵循 Keep a Changelog）。
- 配置项落地进 `config/settings.py`，并提供默认值；敏感配置不硬编码进代码。
- 新文件遵循现有分层：放错层的代码会被要求归位（参照 `core/` vs `tools/` 之分）。

## 5. Avoid（已踩过的坑 / 已知陷阱 —— 不要再犯）

每条都源于本项目真实发生过的修复：

1. **不要把示例表/列名硬编码进系统提示词**（早期写死 `sales/orders/...`，与真实库不一致会误导 LLM）。
   → 改用 `get_relevant_schemas` 返回的真实结构。README 里也不要新增示例 schema。
2. **不要加无界缓存 / 无 TTL 的全局 dict**（图表缓存曾无界增长）。
   → 新增缓存必须带容量上限 + 过期时间。
3. **不要引用不存在的表 / 依赖外部假设**（`checkpoint_cleanup` 曾 `LEFT JOIN conversations`，而该表从不创建，必然报错）。
   → 运行时先探测依赖存在性，再给明确提示。
4. **不要旁边再造重复实现**（`viz_tools.py` 与 `chart_tools.create_chart` 重叠，是死代码，已删）。
   → 新工具先确认没有已有工具能做同样事。
5. **声明了 timeout 就要真正生效**——用线程/进程边界兜住 `exec`，别让死循环卡死进程。
6. **LLM 用的 schema 检索有可靠上限**：`schema_max_relevant_tables` 控制召回量，避免一次塞进过载上下文。

> 更多候选（未实装）：`get_relevant_schemas` 仍基于硬编码关键词映射，建议后续改 Embedding 语义检索；同步版 `create_agent` 缺消息裁剪中间件。
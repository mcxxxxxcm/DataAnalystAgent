# Change Overview：一次补齐 4 项 backlog（提示词缓存 / Redis 多worker / 可观测 / RBAC+限流）

> 复制自 `openspec/changes/_TEMPLATE/`。**310 原则：大白话讲清再动手。**

## Why（为什么做）

`tasks.md` 候选 backlog 里还挂着 4 个未落地能力，本次一次补齐：**B005** LLM 提示词缓存省计费（相同系统提示词每轮全量计费）、**B006** 多 worker + Redis 共享缓存（现为每进程内存缓存，扩 worker 后 result_id 跨 worker 404）、**B007** 可观测 `/metrics`（目前只有 `/api/stats` 快照，缺指标端点）、**B010** 表/列级 RBAC 与速率限制/配额（现仅单 token 全局鉴权 + 工具级 scope，无最小授权与防滥用）。

> 注：本会话网络受限，无法逐行对照 DeepSeek superagent 开源项目；方案按本项目现有分层/安全约束 + 通用 agent 平台最佳实践设计。

## What（做什么 / 不动什么）

- **B005**：提示词固定前缀置顶、动态段置尾（命中 provider 自动磁盘缓存）；可选显式 cache 头注入。默认 `prompt_cache_enabled=False`。
- **B006**：新增 `utils/cache_backend.py` 缓存后端抽象（memory 包装现有 `BoundedTTLCache` / redis 可选），替换 `result_store` 与图表 spec 缓存底层；保持单一写者 + TTL/容量有界 + 非破坏读。默认 `cache_backend="memory"`，Redis 连不上静默回退。
- **B007**：新增 `observability/` 包 + Prometheus 文本 `GET /metrics`。默认 `observability_enabled=False`。
- **B010**：`core/security/rbac.py`（角色→表/列白名单 + 工具 scope）+ `core/security/rate_limit.py`（滑动窗口限流）；`guard_query_sql` 加可选 `column_checker`。默认 `enable_rbac=False`。
- **不做**：不引入完整 OTel SDK（重）——首版落 Prometheus 文本、追踪留接口；不做多语句事务、不替换现有 SQL 校验链（新增为 additive/可选）。
- 影响层级：config / utils / tools / core / agent / middleware / api + observability 新包。

## How（怎么落地,一句概览）

新增或扩展位于各自分层的模块并把所有新能力做成「默认关、additive、可选依赖、失败降级」注入现有链路；四段各带独立测试，最后 `pytest tests/ -q` 全绿、回填 spec/tasks/state-owners 并归档。

---

- 关联模块：全部 backlog 项；涉及 CAP 由四段各自引入。
- 涉及测试：`tests/test_cache_backend.py`、`tests/test_observability.py`、`tests/test_rbac.py`、`tests/test_rate_limit.py`、`tests/test_prompt_cache.py`（+ 回归 `test_single_writer.py` / `test_tool_boundaries.py`）。
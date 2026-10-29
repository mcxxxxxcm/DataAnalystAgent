# Change Proposal：SDD 开发规范完善（一致性 + 关键流程 + 优化路线）

> 设计文档，给**人** review。本 change 只动治理文档，遵循「单一事实来源、避免漂移」的原则组织改动。

## 现状 → 目标

**现状**：OpenSpec 五件套（spec/tasks/design/agreement/terminology）骨架齐，但 (a) 部分 CAP/TASK/TERM 引用已删文件或过时计数；(b) 流程只规定「归档 change」，没规定归档后回填 spec/tasks；(c) backlog 稀疏、无优先级。

**目标**：让治理文档与代码基线一致、流程自带防漂移约束、后续优化方向有优先级可执行。

## 改动清单

### 1. `openspec/specs/spec.md`
- **修 stale**：
  - CAP-EVAL-002：`golden_queries.json` → `eval/cases/`（`schema_linking.json`/`security_deny.json`/`routing_guard.json` 三文件），语义改「多场景分类语料」。
  - CAP-EVAL-003：测试数 76 → 121，补新增测试组名。
- **新增 CAP**（写操作 / 意图路由器 / 压测 / 可观测，均已落地）：
  - §3 core/security：`CAP-SEC-008` 写操作受边界保护（`query_database` 分派 INSERT/UPDATE/DELETE → 返回受影响行数、写后失效 schema 缓存、不入 result_store；`enable_sql_write` 默认关 + HITL 强制人审）。`CAP-SEC-009` 确定性意图路由器 `intent_guard`（query/chart/info/malicious/smalltalk/ambiguous/out_of_scope，deny/clarify 语义；`ENABLE_INTENT_ROUTER` 默认关、仅评测直调未接线 /query）。
  - §7 API：`CAP-API-006` 可观测只读端点 `GET /api/stats`（连接池/线程池/缓存状态，供压测闭环）。
  - §8 Utils：`CAP-UTIL-005` 并发压测工具 `bench.loadtest`（health/ping/query、thread-mode、--dry-run）。
- **更新状态表**：写操作由「候选」改 implemented；补 bench/intent_router 行备注（接线列为后续）。

### 2. `openspec/tasks.md`
- **修 stale**：TASK-EVAL-002 golden 路径；TASK-EVAL-003 76→121。
- **新增 done TASK**（对齐新 CAP）：`TASK-SEC-008` 写操作分派、`TASK-SEC-009` 意图路由器（未接线）、`TASK-API-006` /api/stats、`TASK-UTIL-005` bench.loadtest。
- **扩充 backlog 至 ~10 项**：保留 B001/B002/B003（补优先级），新增 B004..B010，每项含【优先级/成本/收益/关联 CAP/落点】。优先级口径：P0 必做近期 / P1 值得中期 / P2 可选远期。
- 把 `TASK-BACKLOG-004`（已 done）从 backlog 移出到正文对应工具分组下，保持 backlog 恒为 `[todo]`。

### 3. `openspec/terminology.md`
- TERM-013 golden 集路径 → `eval/cases/`。
- 新增 `TERM-014` 意图路由器 intent_guard、`TERM-015` 写操作边界（增删改、HITL 门禁）。

### 4. `openspec/agreement.md`
- 新增 **§2.5 Definition of Done（完成定义）**：change 合入前 checklist——(a) recipe 各步 Validation 已过；(b) `pytest tests/ -q` 全绿；(c) 用户可见变更已更 README、可记变更已更 CHANGELOG；(d) 新增/改能力已回填 `spec.md` 对应 CAP 与新 done TASK；(e) change 目录移出 `changes/` 归档。任一未过不放行。
- 新增 **§6 Keep Docs in Sync**：归档 change 时同步回填 CAP/TASK/TERM；同一候选只允许在 `tasks.md` backlog 维护一处，design/spec/agreement 只用指针引用；发现 stale 立即修。
- §5 Avoid 追加 **#7「不让治理文档漂移 / 各写一套」**：新能力 → 一处 CAP + 对应 TASK + 一处 backlog；不另起炉灶。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 流程约束 | agreement 加 DoD + §6 同步规则 | 防止「归档即脱节」的固有漂移 | 每次 change 多一步回填（约定即成本，但防返工） |
| 路线落点 | 扩 tasks.md backlog 而非新建 ROADMAP | 单一来源，沿用既有编号体系 | 无独立面向干系人的路线图文件 |
| 新 CAP 粒度 | 按能力域补（写操作/意图/可观测/press） | 与既有分节一致 | 状态表需随之维护 |
| 优先级口径 | P0-P2 三档 + 成本/收益 | 可执行、可排期 | 主观评级，需人维护 |

## 兼容性

- 纯文档，无 API/代码/配置改动，无向后兼容问题。CAP/TASK 编号沿用既有命名，不破坏既有引用。
- 新 CAP/TASK 描述的「现状」均与代码基线核实（写操作 / intent_guard / bench /stats / cleanup-orphaned 已在代码与 CHANGELOG 落地）。

## 测试计划

- 无代码/无单测变更。改后跑 `py -m pytest tests/ -q` 确认 121 项仍全绿（治理文档不影响运行时）。
- 手工核对：grep 确认 `golden_queries.json` 不再被 spec/tasks/terminology 引用；新 CAP 在 spec.md 有对应新 done TASK。
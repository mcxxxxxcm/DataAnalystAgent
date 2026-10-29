# Change Recipe：SDD 开发规范完善（执行剧本）

> **给 LLM 的逐步执行清单。** 每一步 = `Context(为什么)` + `Action(做什么)` + `Validation(怎么验证通过)`。
> 执行后：对着每步 Validation 自检一遍，在对应步骤后打 `[x]`。

## Step 1 —— 读约定
- **Context**：本 change 只动治理文档，仍需对齐宪法。
- **Action**：确认本 change 属 `openspec/` 文档层、不触碰代码/红线；采用「单一来源、归档回填」原则（本 change 自己就是「完善规范」的示范）。
- **Validation**：`proposal.md` 已写明分层与兼容性。 `[x]`

## Step 2 —— 修 spec.md 一致性
- **Context**：spec 是能力基线，必须与代码一致，否则误导。
- **Action**：改 `openspec/specs/spec.md`——CAP-EVAL-002 golden 路径→`eval/cases/`、CAP-EVAL-003 76→121、新增 CAP-SEC-008 写操作 / CAP-SEC-009 意图路由器 / CAP-API-006 /api/stats / CAP-UTIL-005 bench.loadtest，更新状态表。
- **Validation**：grep `golden_queries.json` 在 spec.md 不再命中；新增 CAP 命中对应文件。 `[ ]`

## Step 3 —— 修 tasks.md + 扩 backlog
- **Context**：tasks 是执行/验收清单，需与新 CAP 对齐并给出可执行路线。
- **Action**：改 `openspec/tasks.md`——修 TASK-EVAL-002/003 stale；加 done TASK-SEC-008/009、TASK-API-006、TASK-UTIL-005；把 B004 移出 backlog；backlog 扩到 ~10 项（B001..B010），每项含优先级/成本/收益/关联 CAP/落点。
- **Validation**：backlog 至少 9 项 `[todo]` 且每项含优先级；新 done TASK 与新 CAP 一一对应。 `[ ]`

## Step 4 —— 修 terminology
- **Context**：术语表需引用真实文件路径。
- **Action**：改 `openspec/terminology.md`——TERM-013 golden→`eval/cases/`；新增 TERM-014 意图路由器、TERM-015 写操作边界。
- **Validation**：`golden_queries.json` 在 terminology 不再命中；TERM-014/015 存在。 `[ ]`

## Step 5 —— agreement 补流程
- **Context**：流程缺「归档回填」与 DoD，是漂移根因。
- **Action**：改 `openspec/agreement.md`——新增 §2.5 Definition of Done、§6 Keep Docs in Sync、§5 Avoid#7。
- **Validation**：agreement 含 DoD checklist 与归档回填规则；编号与既有小节连续。 `[ ]`

## Step 6 —— 复核
- **Context**：确保一致性改动真实落地、无残留 stale。
- **Action**：grep 全 `openspec/` 确认 `golden_queries.json`（旧路径）+ 过期测试数已清；`py -m pytest tests/ -q` 确认治理文档改动不误伤（仍 121 全绿）。
- **Validation**：grep 无旧引用；测试 121 全绿。 `[ ]`

## Final —— 归档 + CHANGELOG + 提交推送
- **Context**：用户可见/记录性变更落文档，change 归档，提交推送远端。
- **Action**：本 change 目录移出 `changes/` → `archived/`；`CHANGELOG.md` [Unreleased] 追记「SDD 规范完善」；`git commit -m "<主题>(<取舍>)：<说明>"` + `Co-Authored-By`；push 远端（用户明确要求）。
- **Validation**：`git status` 干净；commit 已 push；change 已归档；⑬ CHANGELOG 已更新。 `[ ]`

## Final 自检对照 overview.md How
- 修 stale（spec/tasks/terminology）✓；补 DoD+归档回填（agreement）✓；扩 backlog 带优先级 ✓；push 远端 ✓。 `[ ]`
# Change Overview：SDD 开发规范完善（一致性 + 关键流程 + 优化路线）

> 分层：`openspec/` 治理文档层。不触碰代码/安全红线，直接编辑 `agreement.md` / `specs/spec.md` / `tasks.md` / `terminology.md`。纯文档，不需要新配置/测试。

## Why（为什么做）

OpenSpec 文档骨架完整，但已与代码脱节并缺乏关键流程约束：
- **stale**：`spec.md`/`tasks.md`/`terminology.md` 仍引用已删除的 `eval/golden_queries.json`（语料已迁 `eval/cases/`）；测试数写死 76 而非 121；缺少近期能力（写操作、intent_guard、bench、`/api/stats`、cleanup-orphaned）。
- **流程缺约束**：change 归档后不回填 `spec/tasks`，同一候选在 design/agreement/spec/tasks 多处重复维护 → 漂移。
- **优化方向稀疏**：backlog 仅 3 项，缺少优先级/成本/收益，不足以指导后续投入。

## What（做什么 / 不动什么）

- **做**：
  1. 修一致性：`spec.md`/`tasks.md`/`terminology.md` 对齐现状（golden 路径、测试数、补新 CAP/TASK/TERM）。
  2. 补流程：`agreement.md` 加 §2.5 完成定义(DoD)清单 + §6 文档同步/归档回填规则 + Avoid 反漂移条目。
  3. 扩路线：`tasks.md` backlog 扩到 ~10 项，每项含【动机/落点/优先级(P0-P2)/成本/收益/关联 CAP】，沿用 `TASK-BACKLOG-*` 体系。
- **不做**：不动代码、不改安全红线、不重构既有 CAP 编号、不为 backlog 写实现代码。
- 影响：`openspec/` 下 4 个 markdown。

## How（怎么落地,一句概览）

修 `spec/tasks/terminology` 三处 stale 到当前代码基线，补写操作/intent_guard/bench/stats 的 CAP 与新 done TASK；给 `agreement.md` 加 DoD 与归档回填规则；把 `tasks.md` backlog 扩成带优先级/成本/收益的 ~10 项路线。细节见 `recipe.md`。

## 关联模块

- 涉及测试：无（纯文档）。改完 `pytest tests/ -q` 复核不回归即可。需确认新增 CAP/TASK 描述的「现状」属实（写操作/intent_guard/bench/stats/cleanup-orphaned 均已在代码与 CHANGELOG 落地）。
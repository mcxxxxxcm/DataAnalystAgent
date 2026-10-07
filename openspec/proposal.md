# 项目提案（Project Proposal）

> 项目级 RD 文档，给**人** review 用，回答「这个项目做什么、怎么做、如何验收」。
> 编号规则：`PROP-xxx`。本文档是活文档，随 Q&A 填充、随改动演进。
> 对照参考：sdd-in-action `book-code/specs/proposal.md`（背景与目标 → 功能范围 → 验收标准 → 术语）。

---

## 1. 背景与目标（Background & Goals）

### 1.1 背景

> 【待 Q&A 填充】你愿意做这个项目的原始动机 / 痛点是什么？一句话讲清「不这么做会怎样」。
> 可从 `project.md` 的 Why 引申，但这里要的是更具体的业务/个人背景。

（占位，Q&A 后填写）

### 1.2 目标

> 【待 Q&A 填充】做出来的东西，最终要达成什么可验证的结果？
> 已完成的能力见 `openspec/specs/spec.md`，可作为「现状基线」引用，不必重复罗列。

（占位，Q&A 后填写）

### 1.3 目标用户

> 【待 Q&A 填充】谁用、谁看？各角色的诉求分别是什么？

（占位，Q&A 后填写）

## 2. 功能范围（Functional Scope）

### 2.1 做什么（In scope）

> 【待 Q&A 填充】本期交付的核心能力清单。
> 可引用 `openspec/specs/spec.md` 的 CAP-xxx 作为能力基线。

（占位，Q&A 后填写）

### 2.2 不做什么（Non-goals，明确排除）

> 防范围蔓延。目前 `project.md` 已列一批，Q&A 里确认是否增减。

（占位，Q&A 后填写）

### 2.3 技术约束

> 【待 Q&A 填充】技术栈 / 部署 / 外部依赖 / 运行方式等硬约束。
> 现技术栈见 `openspec/agreement.md` §1（Python/LangGraph/FastAPI/PostgreSQL）。

（占位，Q&A 后填写）

## 3. 验收标准（Acceptance Criteria）

### 3.1 功能验收

> 【待 Q&A 填充】逐条 checkbox，对应 2.1 的能力，可验证。

- [ ] （占位）

### 3.2 性能 / 成本验收

> 【待 Q&A 填充】耗时、token/成本、吞吐上限等；参考 agreement §5（成本控制是既有红线）。

- [ ] （占位）

### 3.3 安全 / 边界验收

> 安全红线见 `openspec/agreement.md` §3，逐条映射为可测的验收项。

- [ ] （占位）

## 4. 术语定义（Glossary）

> 术语表维护在独立文件 `openspec/terminology.md`，本文档只负责在「出现歧义处」引用。Q&A 后同步。

（引用 `openspec/terminology.md`）

---

*规范版本：v0.1（草稿，待 Q&A 填充） | 维护人：@mcx | 更新：2026-10-07*
# CLAUDE.md — Data Analyst Agent 协作约定

本仓库已接入 **OpenSpec（Spec-Directed Development）** 纯 Markdown 约定。给 AI / 协作者的第一份指令；详细宪法与已知陷阱在 `openspec/agreement.md`。

## 第一铁律：动手前先读约定

改动本仓库**任何文件之前**，先读 `openspec/agreement.md`（分层、安全红线、Avoid 陷阱），并据它判断本次改动是否触碰红线、应归到哪一层。

## 改动工作流

- **trivial 改动**（一行修复、重命名、纯注释）：可直接做，但回复里点一句「trivial 跳过 change 流程」。
- **其他改动（默认）**：**必须先建 OpenSpec change**，再动手——
  1. 复制 `openspec/changes/_TEMPLATE/` → `openspec/changes/<slug>/`。
  2. 填 `overview.md`(310)、`proposal.md`(设计)、`recipe.md`(逐步剧本,每步 Context/Action/Validation)。
  3. 请用户在开始前确认 change。确认后**严格按 `recipe.md` 执行**，每步过 Validation。
  4. 完成 `pytest tests/ -q` 全绿 → 收尾自检 → 归档 change。
- 用户明确说「直接做 / 不用 spec」时，遵循用户的即时指令优先于本流程。

## 硬性工程标准（违反即打回）

- **安全红线见 agreement §3**：SQL 校验、HITL、任意代码执行默认关、工具边界，一个都不能破。
- 改动必带测试；`pytest tests/ -q` 必须全绿。
- 代码注释中文；change 文档中英混合。
- 用户可见变更更新 `README.md`，记录性变更追加 `CHANGELOG.md`。
- 配置进 `config/settings.py` 并给默认值；不硬编码。
- 提交信息用中文一句主题，如 `git commit -m "<主题>(<取舍>)：<说明>"`，并附 `Co-Authored-By`。

## Avoid 速览（详见 agreement §5）

系统提示词不硬编码示例表；缓存必须有界；不引用不存在的表；不造重复实现；声明 timeout 就真正生效。
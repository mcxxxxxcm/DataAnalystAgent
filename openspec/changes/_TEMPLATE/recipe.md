# Change Recipe：{主题}（执行剧本）

> **给 LLM 的逐步执行清单。** 每一步 = `Context(为什么)` + `Action(做什么)` + `Validation(怎么验证通过)`。
> 这是本 change 和普通 PR 描述最大的区别：agent 照着这个剧本一步不落地跑,不会跑偏。
> 执行后:**对着每步 Validation 自检一遍**,在对应步骤后打 `[x]`。

## Step 1 —— 读约定
- **Context**: 动手前先对齐项目宪法,避免违反分层 / 安全红线。
- **Action**: 读取 `openspec/agreement.md`,确认本 change 落在哪一层、有没有触碰安全红线、是否命中 Avoid 陷阱。
- **Validation**: 在 `proposal.md` 里写清本 change 属于哪个分层。 `[ ]`

## Step 2 —— {动作名}
- **Context**: （为什么做这一步）
- **Action**: （具体做什么,给出真实文件路径）
- **Validation**: （可验证的结果,如某命令输出 / 新增函数签名） `[ ]`

## Step 3 —— {动作名}
…
## Step N —— 测试
- **Context**: 本仓库测试是硬门槛。
- **Action**: 新增/更新测试文件 → `pytest tests/ -q`。
- **Validation**: 全绿,且新用例覆盖本 change 关键路径。 `[ ]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How 承诺逐条核对是否兑现。
- 更新 `README.md` / `CHANGELOG.md`(如有用户可见变化)。
- 本 change 目录移出 `changes/`(归档或删除)。
- 提交信息用中文一句主题,如 `git commit -m "<主题>(<取舍>)：<说明>"`。 `[ ]`
# Change Overview：确定性回归评测(坏case/错误案例/评测集)

> 复制本目录为 `openspec/changes/<your-slug>/`,填写下面三节。**310 原则:每节用大白话讲,能讲清再动手。**

## Why(为什么做)

现在评测集只有 5 条、只测「表检索排序 + 写操作拦截」,没有坏 case、没有错误案例(拒答/澄清/报错)、`sql_contains` 还是从没被校验的死字段。改动 schema/安全/提示词时没有抓手,无法防回归,也无法验证「意图识别」做得好不好。

## What(做什么 / 不动什么)

要新增/修改:
- 新增确定性 `intent_guard.py` 意图路由器,把 NL 分类成 query/chart/info/malicious/smalltalk/ambiguous/out_of_scope(纯逻辑、无 DB/LLM,复用 schema_linking 做实体命中判定)。
- 评测集重构成三类:表检索 / SQL 安全拦截 / NL 路由判定,坏 case + 错误案例结构化入库。
- `run_eval.py` 重写为多场景聚合 harness,输出每例 PASS/FAIL + 指标,任一失败即非零退出(可进 CI/pytest gate)。
- 顺手修掉 `sql_contains` 死字段。

**明确不做**:这一轮**不把路由器接进线上 `/query` 入口**(避免未经验证就改变运行时行为),只作为评测断言体 + 单测;接线列为后续 change。

影响层:`core`(新增 intent_guard)、`eval/`(数据结构 + harness)、`tests/`、`config/`(阈值默认值)、README/CHANGELOG。

## How(怎么落地,一句概览)

新增纯逻辑意图路由器当确定性判定入口 → 把评测集按三类场景结构化重建 → 重写 harness 聚合评分并设硬门槛(误放行=0) → 补齐单测 + pytest 全绿。细节见 `recipe.md`。

---

- 关联 issue / 关联模块:(可空)
- 涉及测试:`tests/test_eval_text2sql.py`(更新)、`tests/test_eval_regression.py`(新增)、`tests/test_intent_guard.py`(新增)
# 坏 case / 错误案例台账

> 每个条目记录：来源(日志/人工种子)、历史失败、当前是否修复、修复后行为。
> 机器侧的可断言回归在 `eval/cases/` 三个 JSON 里；这里是人读的补充说明与「已知盲点」清单。

## 一、已纳入评测集(可断言回归)

| case id | 类别 | 一句话 | 来源 |
|---------|------|--------|------|
| s01-s06 | schema_linking | 订单/销售/用户/产品 表检索命中与排序 | nl/log |
| sec01-05 | security_deny | DELETE/DROP/TRUNCATE/UPDATE/堆叠注入 应被 SQL 校验层拒绝 | nl/seed |
| accept01-02 | security_deny | 合法聚合/过滤 SELECT 必须放行(防误杀) | nl/seed |
| r01-r12 | routing_guard | query/chart/info 放行；malicious/smalltalk/out_of_scope 拒答；ambiguous 澄清 | nl/log/seed |
| r09 | routing_guard | 「被删除的订单」含删除字样但合法 → 不误杀(控制组) | seed |

## 二、已知盲点(未修，勿当断言误用)

- **恒真注入 `WHERE name='o' OR '1'='1'` 会被 `SQLValidator` 放行**。
  探明：`sql_validator` 的 `_detect_injection` 只兜「堆叠语句 + 危险注释」，不拦单语句恒真注入。
  → 不要把它放进 `security_deny` 的 deny 断言(会假失败)；它属于「后续应在 SQL 层补 OR-恒真检测」的待办。
  → NL 层 `intent_guard` 已能拦 `or 1=1`(r12)。
- **评测索引必须传同义词表**。旧 `run_eval` 的合成索引没传 `build_synonym_map()`，导致「今年订单总数」这类核心词 FALLBACK 未命中——那是对不贴近生产的索引在假评测。现已统一用带同义词的合成索引。

## 三、坏 case 采集来源

- `logs/tool_calls.jsonl`：真实调用记录，`success=false` 或执行异常的条目 → `py -m eval.mine_badcases` 会 dump 出来，供半人工沉淀成新 case。
- `logs/agent.log`：agent 链路日志，异常堆栈常含失败 SQL。
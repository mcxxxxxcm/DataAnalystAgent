# Change Recipe：注入检测加固 + 坏 case 自动扩集（执行剧本）

> 给 LLM 的逐步执行清单。每步 = Context + Action + Validation。执行后逐条自检打 `[x]`。

## Step 1 —— 读约定 + 确认分层
- **Context**: 安全相关改动有硬红线（agreement §3），且要低误杀。
- **Action**: 读 `openspec/agreement.md`；确认改动落 `core/security` + `eval`，不触写操作/HITL、不放宽任何权限。
- **Validation**: 已确认分层与红线。 `[ ]`

## Step 2 —— sql_validator 补恒真/恒假字面比较 pattern
- **Context**: `_detect_injection` 只拦注释+多语句；恒真注入漏网。
- **Action**: 在 `core/security/sql_validator.py` 加类级常量 `TAUTOLOGY_PATTERNS`（两侧均字面量）：
  - 数字 vs 数字：`(?<![A-Za-z0-9_])\d+\s*(=|<|>|<=|>=|<>|!=)\s*\d+`。
  - 引号串 vs 引号串：`'[^']*'\s*(=|<|>|<>|!=)\s*'[^']*'`。
  在 `_detect_injection` 末尾：任一 pattern 命中（`re.search(sql_lower, IGNORECASE|DOTALL)`）即 `return True`。**不要**加注释遮蔽/`(OR|AND)` 前缀 pattern（后者会把 `region='Jingdong'` 误判；串比较 pattern 已天然避开有序前缀）。
- **Validation**: 独立小脚本确认
  `validator.validate("SELECT * FROM sales WHERE region='x' OR '1'='1'")` 不通过、`_.validate("... WHERE region='Jingdong' AND amount>100")` 通过。 `[ ]`

## Step 3 —— 补 mint_badcases 沉淀纯函数 + CLI
- **Context**: 坏 case 只 dump 不沉淀，回归扩集靠人手。
- **Action**: 在 `eval/mine_badcases.py` 加：
  - `_norm_sql(sql)`：`strip` + 吞空白 + 大写（幂等 key）。
  - `propose_security_denies(records, existing_sqls, limit=200)`：扫 `query_database` 失败且 `error` 含「校验|拒绝|allow|denied|reject」的调用，取 `input_args.query`；`_norm_sql` 去重；排除已在 `existing_sqls`（同样归一）中的；产出 `{id:'sec-auto-<n>', scenario:'security_deny', sql, deny_expected:true, source:'log', note:'坏case自动沉淀'}`。
  - `main()` 加 `--sink-security` 与 `--apply`：`--sink-security` 读现存 `security_deny.json` 的 `sql` 集合，打印拟新增；`--apply` 且非空时 append 并写回。
- **Validation**: 单测覆盖去重/跳过/归一；`--sink-security` 无 `--apply` 不写文件。 `[ ]`

## Step 4 —— 测试（直接单测，不写语料）
- **Context**: 安全改动必须带测试；误杀控制用直接断言锁死；`security_deny.json` 的配套用例由 `eval-corpus-expansion` change 写（单一写者）。
- **Action**: `tests/test_security.py` 增——拒：`SELECT * FROM sales WHERE 1=1`、`... WHERE id=1 OR 1=1`、`SELECT * FROM users WHERE name='a' OR 'a'='b'`；放行控制：`SELECT * FROM sales WHERE region='Jingdong'`、`SELECT * FROM orders WHERE amount>100`、`SELECT * FROM sales WHERE id=1`。新增 `tests/test_mine_badcases.py`（`propose_security_denies` 去重/跳过/归一/`--apply` 才写）。
- **Validation**: `py -m pytest tests/test_security.py tests/test_mine_badcases.py -q` 通过。 `[ ]`

## Step 5 —— 全量回归
- **Context**: 新增/改安全逻辑不能破坏既有。
- **Action**: `py -m pytest tests/ -q`。
- **Validation**: 全绿。 `[ ]`

## Final —— 收尾
- 更新 `README.md`（安全设计注入层补一句）/`CHANGELOG.md`。目录移 `openspec/archived/`。中文主题提交。 `[ ]`
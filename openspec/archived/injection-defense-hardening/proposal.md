# Change Proposal：注入检测加固 + 坏 case 自动扩集

> 设计文档。补齐容错层只读漏网的布尔注入，并把坏 case 沉淀做成可回归管道。

## 方案

### 现状
- `_detect_injection`（`core/security/sql_validator.py:269`）只做两件事：危险注释 pattern + `sqlparse.split` 多语句检测。
- 恒真注入 `SELECT ... WHERE id=1 OR '1'='1'`、`AND 1=1`、`x='a' OR 'a'='a'`、`--` 注释掉 WHERE 后接恒真：这三个类在 SQL 层**全部放行**（不触发任何已有 pattern）。
- `eval/badcases.md` 明记「恒真注入 `OR '1'='1'` 当前在 SQL 层不拦，记作待办」。
- `mine_badcases.py` 只能 dump 失败调用给人工看，不能自动沉淀成 `security_deny.json` 回归用例。

### 目标
- SQL 校验层拦截**字面量级恒真/恒假布尔注入**，且**绝不误杀**合法 `列='值'` 过滤（低误杀是安全改动铁律）。
- `mine_badcases` 一条命令即可把已拒失败调用去重沉淀进语料，回归扩集自动化。

### 改动清单
- **修改** `core/security/sql_validator.py`：
  - 新增 `TAUTOLOGY_PATTERNS`（恒真/恒假布尔注入，仅匹配「两侧都是数字或引号串」）：
    - 数字 vs 数字：`1=1`、`0=0`、`2>1`、`1<2`、`1=2` 等：`(?<![A-Za-z0-9_])\d+\s*(=|<|>|<=|>=|<>|!=)\s*\d+`。
    - 引号串 vs 引号串：`'a'='a'`、`'a'='b'`：`'[^']*'\s*(=|<|>|<>|!=)\s*'[^']*'`。
  - 在 `_detect_injection` 末尾跑这两组 pattern；任一命中即返回 `True`。
  - 关键约束：**两侧必须都是字面量**——`region='Jingdong'`、`amount>100` 左是标识符，不命中 → 不误杀。
- **修改** `eval/mine_badcases.py`：
  - 新增纯函数 `propose_security_denies(records, existing_sqls, denied_categories=…) -> list[dict]`：扫 `tool_name=='query_database'` 且 `error` 命中「校验/拒绝」字样（或 `success is False`）的调用，抽 `input_args.query` → 规范化（`sqlparse.format` 或简单 strip/大写）作去重 key；跳过与已有 `security_deny.json` 中 `sql` 一致的；产出 `{id, scenario:'security_deny', sql, deny_expected:true, source:'log', note:'坏case自动沉淀'}`。
  - CLI：`py -m eval.mine_badcases --sink-security` 打印拟沉淀（dry-run）；加 `--apply` 真写入 `security_deny.json`（幂等：按 sql 去重后 append）。
  - 默认不开 sink（保持只读 dump 行为）。
- **测试**：
  - `tests/test_security.py`：恒真/恒假注入被拒；`列='值'`/`amount>100` 合法过滤不误杀。
  - `tests/test_mine_badcases.py`（新增）：`propose_security_denies` 去重、跳过已存在、规范化 key。
- **语料**：`security_deny.json` 的配套拒/放用例由 `eval-corpus-expansion` change 新增（避免两个 change 同时写同一文件，单一写者）；本 change 只写 validator 与 mine_badcases 代码及其直接单测。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 只拦「字面量 vs 字面量」恒真 | 字面量比较 | 安全改动低误杀第一：`列='值'` 合法过滤绝不能被当注入；恒真是最高危 | `列='列'`（同列比较）不拦，但极罕见且不构成注入 |
| 是否拦 `UNION SELECT` | 不拦 | 合法跨表合并是分析刚需（`estimate_complexity` 也算了 UNION），拦了会误杀 | 少一类注入防线，靠 NL 层 + 白名单兜 |
| 坏 case 沉淀默认 dry-run | `--sink-security` 默认只打印 | 自动写语料风险高（噪音/失真），人类同意（`--apply`）再落库 | 非全自动，需一次显式 flag |
| 沉淀按规范化 SQL 去重 | strip/大写归一 | 幂等、可重复运行 | 简单归一可能漏等价不同写法，后续可加 sqlparse 归一 |

## 兼容性
- 校验层多拦的是真正注入类，合法 SELECT/写操作不受影响；控制组回归用例锁死不误杀。
- `mine_badcases.py` 默认行为不变（只读 dump）；`--sink-security` 是纯增量。
- 返回结构、工具签名、配置**均不变**（无新配置）。

## 测试计划
- `tests/test_security.py` 新增 ~8 例：恒真数字/恒真串/恒假/注释遮蔽拒绝；`region='Jingdong'`、`amount>100`、`id=1` 放行控制组。
- `tests/test_mine_badcases.py` 新增 ~5 例：去重、跳过已有、规范化 key、dry-run 不写、apply 后才写。
- `eval/run_eval.py` 用扩充后的 `security_deny.json` 断言「该拒必拒、误放行=0」。
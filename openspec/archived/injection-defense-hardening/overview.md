# Change Overview：注入检测加固 + 坏 case 自动扩集（Injection Defense Hardening）

> 收割 `eval/badcases.md` 记的唯一 SQL 层待办：恒真注入 `OR '1'='1'` / `1=1` 等当前不拦；并把坏 case 发现从「人工 dump」升级为「可在 CI 自动沉淀成回归用例」。

## Why（为什么做）

`SQLValidator._detect_injection` 目前只拦「危险注释 + 多语句堆叠」，对**恒真/恒假布尔注入**（`WHERE id=1 OR '1'='1'`、`AND 1=1`、`x='a' OR 'a'='a'`）在 SQL 层放行；NL 层 `intent_guard` 能兜住一部分，但只读依赖校验层的路径（HITL 展示、独立工具调用）仍裸露。同时 `mine_badcases.py` 只 dump 不做沉淀，坏 case 回归扩集靠人手抄。

## What（做什么 / 不动什么）

- **修改** `core/security/sql_validator.py`：在注入检测层补「布尔恒真/恒假字面比较」pattern，命中即 `INJECTION_ATTEMPT` 拒绝。
- **修改** `eval/mine_badcases.py`：新增 `--sink-security [--apply]`，把被校验层拒绝的 query_database 失败调用（按规范化 SQL 去重、幂等避开已存在 case）自动沉淀到 `eval/cases/security_deny.json`。
- **测试** 增改 `tests/test_security.py` 与 `tests/test_mine_badcases.py`。`security_deny.json` 的配套拒/放用例由 `eval-corpus-expansion` change 落地，本 change 不写语料（单一写者）。
- **不做**：不拦正常 UNION（合法分析需要，低误杀优先）；不拦「列=字面量」的合法过滤；不补易误杀的注释遮蔽 pattern；不改变写操作/HITL 语义；不引入 AST 求值器。

## How（怎么落地，一句概览）

在 `_detect_injection` 里加一组**两侧都是字面量**（数字或引号串）的恒真/恒假比较正则（`数字=数字`、`'串'='串'`），仅在两侧都非标识符时判定，天然不误伤 `列='值'`；并给 mine_badcases 加一个去重沉淀纯函数。

---

- 关联模块：`core/security/sql_validator.py` · `eval/mine_badcases.py` · `eval/cases/security_deny.json`
- 关联 CAP：CAP-SEC-001（校验）/ CAP-SEC-002 / CAP-EVAL-002
- 关联 backlog：TASK-BACKLOG-009
- 涉及测试：`tests/test_security.py`（增）· `tests/test_mine_badcases.py`（新增）
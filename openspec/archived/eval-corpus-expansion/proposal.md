# Change Proposal：评测语料扩集 + 回归加固

> 设计文档。纯语料扩充，不加判定逻辑，保证确定性。

## 方案

### 现状
- `schema_linking.json`：6 例（单表召回 + s03 跨表 + s06 排序）。缺：更多多表关联、列注释驱动、聚合/计数召回的上界与边界。
- `routing_guard.json`：12 例。缺更多图表词、结构询问、清空类恶意、更多合法控制组。
- `security_deny.json`：6 例（DDL/写/堆叠/控制组）。缺恒真/恒假字面比较注入。

### 目标
- 每个 scenario 覆盖面加厚，且**全部确定性**可过 `eval/run_eval.py`。

### 改动清单（新增用例，只加不改判定）

#### `schema_linking.json`（基于 `build_test_index`：sales/users/orders/products + 同义词表）
| id | nl | expected | 覆盖点 |
|----|----|----------|--------|
| s07 | 各地区销售额和注册用户数 | [sales, users] | 多表关联同时召回 |
| s08 | 按商品类别统计平均价格 | [products] | 列名(price)驱动召回 |
| s09 | 会员等级分布情况 | [users] | 列注释(vip_level=会员等级)驱动 |
| s10 | 每个订单包含的商品与用户 | [orders, products] | 三表出二：orders+products 优先 |
| s11 | 销售额超10万的订单 | [sales, orders] | 跨表：sales + orders 双命中 |

> 背调：`s08` 的 `price` 是 products 列名 token → 命中；`s09` 的 `会员等级` 命中 users 列注释；`s11` `销售`→sales、`订单`→orders。均需落在 top-3。

#### `routing_guard.json`
| id | nl | expected_category | 覆盖点 |
|----|----|-------------------|--------|
| r13 | 画个折线图看每月销售趋势 | chart | 折线图词 + 销售实体 → chart |
| r14 | 各地区销售占比，画个饼图 | chart | 饼图/占比词 + 销售实体 |
| r15 | products 表都有哪些列 | info | 结构词 + 实体（英文表名也命中 sales==products 不同）|
| r16 | 清空所有订单数据 | malicious | 中文清空类破坏 → 拒绝 |
| r17 | 查询销售和订单的总金额 | query | 合法聚合、无双清单 → 放行 |

> 背调：`r13/r14` 有销售→sales 实体且 `_CHART_WORDS`（折线/饼图/占比）→ CHART；`r15` products 实体 + `有哪些列`→INFO；`r16` 命 `_CN_DESTRUCTIVE`；`r17` 只聚合双表→QUERY。

#### `security_deny.json`（挂钩本轮注入加固）
拒（`deny_expected:true`）：恒真数字、恒真串、恒假比较、sleep：
- `SELECT * FROM sales WHERE 1=1`
- `SELECT * FROM sales WHERE id=1 OR 1=1`
- `SELECT * FROM users WHERE name='a' OR 'a'='b'`
- `SELECT pg_sleep(5)`
放行控制（`false`，绝不误杀）：
- `SELECT * FROM sales WHERE region='Jingdong'`（字面量 vs 标识符，不是恒真）
- `SELECT * FROM orders WHERE amount > 100`（常量过滤，不是恒真）

> 背调：`region='Jingdong'` / `amount>100` 左是标识符，不命中「双字面量比较」pattern，必须放行——锁死不误杀。

### 不动
- `run_eval.py` 的 `evaluate_case` / `_routing_deny_expect` / `build_test_index` 均不改。（若某新用例 FAIL，只允许调整该用例的 `expected*` 到确定性真值，并注明。）

## 取舍 / 风险
| 决策点 | 选了什么 | 理由 |
|--------|----------|------|
| 语料 vs 判定逻辑 | 只加语料 | 判定逻辑变更又会引入不确定性与回归风险；本轮纯扩充 |
| 新用例 FAIL 处理 | 只调 expected 至真值 | 判定是确定性的，expected 反映真实应然 |
| 安全拒/控制比例 | 拒 4 + 控制 2 | 覆盖注入新防线同时锁死不误杀 |
| 是否引入新 scenario | 否 | 沿用现有三类，保持 harness 稳定 |

## 兼容性 / 回归
- 只增用例，既有用例不动 → 既有断言不受影响。
- 新增拒绝类用例需「注入加固 change」先合入才全绿（二者同轮实施，最终一起回归）。
- `py -m eval.run_eval` 任一 FAIL → 修改该用例 expected 后再跑，直至全 PASS。
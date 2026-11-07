# Change Overview：Embedding schema 语义检索（Embedding Schema Retrieval）

> 给 `get_relevant_schemas` 补一个**可选**的语义重排层：关键词评分仍打底（零新依赖、默认关、行为不变），部署可显式开启向量相似度把表/列注释与用户查询做语义对齐。

## Why（为什么做）

`rank_relevant_tables` 仍是纯关键词/同义词打分（`core/database/schema_linking.py`）。表多、同义表达新或措辞偏离关键词时召回不稳，而项目一直以来靠关键词与同义词映射兜底。Backlog TASK-BACKLOG-001 想引入语义检索，但全量引入 embedding 依赖与向量库成本高、且默认行为会变、评测非确定性。

## What（做什么 / 不动什么）

- **修改** `core/database/schema_linking.py`：加**纯函数** `rerank_with_embeddings(query, candidates, index, embed_sim, weight)`——把用户查询与候选表的「表名+注释+列注释」合成文本做相似度打分，与关键词分加权混合后重排。权重 0 / 无 embedder 时不改变现有顺序（**默认纯粹关键词**）。
- **修改** `config/settings.py`：新增 `schema_embed_enabled: bool=False` 与 `schema_embed_fn: Optional[str]=None`（可选 embedder 的点分导入路径，默认空 = 不启用）。
- **可选接线**：`core/database/schema.py` 的 `get_relevant_schemas` 在 `schema_embed_enabled=True` 且 embedder 能构造时调用重排；任一失败**静默回退**纯关键词（记忆为加分项，非强依赖——遵循低风险原则）。
- **测试**：`tests/test_schema_embed.py` 注入确定性造假 embed 相似度，覆盖重排生效 + 权重 0 顺序不变 + 启用失败回退。
- **不做**：不内置具体 embedding 供应商/向量库/网络调用（保持零新依赖、默认零行为变化）；不把重排做成硬依赖；不改变 `schema_max_relevant_tables` 召回预算。

## How（怎么落地，一句概览）

加一个纯函数把关键词 Top-K 候选按「查询×候选合成文本」的相似度加权重排，配一个默认关的配置与可选 embedder 钩子；默认行为与现在逐字节一致。

---

- 关联模块：`core/database/schema_linking.py` · `core/database/schema.py` · `config/settings.py`
- 关联 CAP：CAP-DB-003（相关表召回）· TASK-BACKLOG-001
- 涉及测试：`tests/test_schema_embed.py`（新增）· `tests/test_schema_linking.py`（保持通过）
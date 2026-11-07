# Change Proposal：Embedding schema 语义检索

> 设计文档。可选语义重排，默认零变化，避免引入重依赖与不可确定性。

## 方案

### 现状
- `rank_relevant_tables(query, index, ...)`（`schema_linking.py:179`）：分词 → `score_table` 加权（表名 3.0 / 同义词 2.5 / 列名 1.5 / 注释 1.2）→ Top-K；无命中才回退 recent/priority。
- `SchemaManager.get_relevant_schemas`（`schema.py:188`）调用它。当前**无任何语义/向量信号**，措辞新颖或专有名词漂移时召回不稳。

### 目标
- 提供一个**纯函数**把「语义相似度」叠加到关键词分上，可选启用，默认关零变化。
- 部署可通过配置挂一个 embedder（返回查询与候选文本相似度），失败静默回退纯关键词。

### 改动清单
- **修改** `core/database/schema_linking.py`：
  - `TableIndex.add` 额外缓存 `vector_text`（表名 + 表注释 + 列名 + 列注释拼接的规范化文本），供 embedder 生成候选向量用（不存向量本身，保持零新依赖）。
  - 新增：
    ```python
    def rerank_with_embeddings(query, candidates, index, embed_sim, weight=1.0) -> List[ScoredTable]:
        """把 query×候选合成文本的相似度与关键词分加权后重排。
        embed_sim(query:str, table_text:str)->float 返回 [0,1] 相似度；
        weight==0 或无 embed_sim 时顺序不变。稳定排序按 (table,) 兜底。"""
        if weight == 0 or not embed_sim:
            return candidates
        ...
    ```
    实现：对每个候选用 `index` 里对应表的 `vector_text` 调 `embed_sim(query, text)`；`cand.score = round(cand.score + weight * sim, 2)`；`sort(key=lambda s:(-s.score, s.table))`。
  - 不动 `score_table` / `rank_relevant_tables` 现有逻辑（关键词仍是基座 + 兜底）。
- **修改** `config/settings.py`：新增
  - `schema_embed_enabled: bool = Field(default=False, ...)`
  - `schema_embed_fn: Optional[str] = Field(default=None, description="可选 embedder 点分导入路径，工厂形如 f()->callable(query, table_text)->float；空=不启用")`
  （遵循少设置约定：不设向量库、模型名等一堆参数，仅一个开关 + 一个钩子。）
- **可选接线** `core/database/schema.py`：`get_relevant_schemas` 在 `schema_embed_enabled=True` 时尝试动态 import `schema_embed_fn` 并缓存一个 embedder；成功 → 对 `rank_relevant_tables` 结果再 `rerank_with_embeddings`；异常 → 打印 warning 并**继续纯关键词**（静默降级）。
- **测试** `tests/test_schema_embed.py`（纯逻辑，无网络）：
  - 假 embed_sim 按表名返回相似度 → 断言重排把目标表顶上、关键词分低的表被反超。
  - `weight=0` → 顺序与纯关键词一致。
  - `embed_sim=None` → 原样返回。
  - 稳定排序兜底（同分按表名）。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 是否内置具体 embedding 实现 | 不内置，只留钩子 | 零新依赖、默认零行为变化；具体供应商由部署注入 | 需部署自己接 embedder 才有语义收益 |
| 重排是叠加还是替换关键词 | 叠加（weight 融合） | 关键词是可信基座，语义仅作增量校准，避免语义噪声拉坏稳定行为 | 语义分高才能显著影响排序 |
| 默认开关 | `schema_embed_enabled=False` | 保守低风险，接通前无副作用；与 intent_router/admission 同理 | 需显式开启 |
| embedder 失败处理 | 静默回退关键词 | 「记忆/增强为加分项，非强依赖」原则；可观测性足够（warning） | 失败时无语义收益 |
| 是否存向量 | 不存 | 避免引入向量存储依赖与一致性测试成本 | 每次查询重建合成文本（成本由 embedder 侧承担） |

## 兼容性
- `schema_embed_enabled=False`（默认）时 `get_relevant_schemas` 返回与现在**逐字节一致**；`rank_relevant_tables` 接口不变。
- 新增配置都有默认值；无新依赖；无新数据库/网络调用（默认路径）。
- 评测保持纯关键词，不受影响。

## 测试计划
- `tests/test_schema_embed.py`：假 embed 重排生效、权重 0/无 embedder 顺序不变、稳定排序兜底。
- `tests/test_schema_linking.py`（既有）保持通过，证明默认路径未被破坏。
- 全量 `py -m pytest tests/ -q` 回归。
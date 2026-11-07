# Change Recipe：Embedding schema 语义检索（执行剧本）

> 给 LLM 的逐步执行清单。

## Step 1 —— 读约定 + 少设置核对
- **Context**: 引入语义能力但绝不能打破「默认纯关键词 / 零新依赖 / 行为不变」。
- **Action**: 读 `openspec/agreement.md`；确认只加一个开关 + 一个钩子，不新增依赖、不内置供应商。
- **Validation**: 已确认不越少设置约定。 `[ ]`

## Step 2 —— schema_linking 加 vector_text + 重排纯函数
- **Context**: 语义重排要在关键词基座上做增量，且必须是纯函数便于确定性测试。
- **Action**: 在 `core/database/schema_linking.py`：
  - `TableIndex.add` 里多缓存 `vector_text`：`' '.join([table, table_comment or '', *列名, *列注释]).strip().lower()`。
  - 新增 `rerank_with_embeddings(query, candidates, index, embed_sim, weight=1.0)`（见 proposal 签名），`weight==0 or embed_sim is None` → 原样返回；否则 `score = round(cand.score + weight * embed_sim(query, text), 2)`，`sort key=(-score, table)`。
- **Validation**: 纯函数可被单测调用；不 import DB/网络。 `[ ]`

## Step 3 —— config 加开关 + 钩子
- **Context**: 是否启用语义重排由部署决定，默认关。
- **Action**: `config/settings.py` 新增 `schema_embed_enabled=False`、`schema_embed_fn: Optional[str]=None`（说明：可选项分导入 embedder 工厂 `f()-> callable(query, table_text)->float`）。
- **Validation**: `test_settings_defaults.py` 通过（或补默认断言）。 `[ ]`

## Step 4 —— SchemaManager 可选接线（静默降级）
- **Context**: 让开关真正生效，但失败绝不阻断查询。
- **Action**: `core/database/schema.py` 的 `get_relevant_schemas`：在 `rank_relevant_tables` 得到 `candidates` 后，若 `settings.schema_embed_enabled`：
  - 尝试 `_load_embedder()`（缓存于实例；`importlib.import_module(schema_embed_fn)` 取可调用工厂 → 调用得 `embed_sim`）；异常 → `print` warning + 返回纯关键词候选。
  - 成功 → `rerank_with_embeddings(query, candidates, index, embed_sim, weight)`。
- **Validation**: 未配置 `schema_embed_fn` 或导入失败时，返回与纯关键词一致；配置假 embedder（点分到测试模块）时重排生效。 `[ ]`

## Step 5 —— 测试
- **Action**: 新增 `tests/test_schema_embed.py`（纯逻辑，假 embed_sim）：
  - 按表名返回相似度 → 断言目标表被重排上浮、低关键词分被反超。
  - `weight=0` 与 `embed_sim=None` → 顺序与纯关键词一致。
  - 稳定排序兜底（同分按表名）。
- **Validation**: `py -m pytest tests/test_schema_embed.py tests/test_schema_linking.py -q` 通过。 `[ ]`

## Step 6 —— 全量回归
- **Action**: `py -m pytest tests/ -q`。
- **Validation**: 全绿（默认路径与之前一致）。 `[ ]`

## Final —— 收尾
- 更新 `README.md`（Schema Linking 检索简述补语义重排开关）与 `CHANGELOG.md`。目录移 `openspec/archived/`。中文主题提交。 `[ ]`
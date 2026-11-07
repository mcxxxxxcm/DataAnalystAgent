"""
Embedding 语义重排（可选，默认零行为变化）测试。

覆盖 schema_linking.rerank_with_embeddings：语义分叠加关键词分重排、权重0/无embedder顺序不变、
稳定排序兜底；以及配置默认关闭。纯逻辑，无网络/向量库。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from core.database.schema_linking import (
    TableIndex, ScoredTable, rank_relevant_tables, rerank_with_embeddings,
)


def _index():
    idx = TableIndex()
    idx.add("sales", [{"name": "region", "comment": "地区"},
                      {"name": "revenue", "comment": "销售额"}], "销售表")
    idx.add("products", [{"name": "price", "comment": "价格"}], "产品表")
    return idx


def test_weight_zero_keeps_keyword_order():
    idx = _index()
    cands = [ScoredTable("sales", 3.0, ["表名命中"]), ScoredTable("products", 2.0, ["注释命中"])]
    out = rerank_with_embeddings("q", cands, idx, lambda q, t: 1.0, weight=0)
    assert [c.table for c in out] == ["sales", "products"]


def test_no_embed_sim_keeps_order():
    idx = _index()
    cands = [ScoredTable("sales", 3.0, []), ScoredTable("products", 2.0, [])]
    out = rerank_with_embeddings("q", cands, idx, None)
    assert [c.table for c in out] == ["sales", "products"]


def test_embed_reranks_low_keyword_to_top():
    idx = _index()
    # 关键词给 products 低分，语义给它满分 → 反超 sales
    cands = [ScoredTable("sales", 3.0, ["表名命中"]), ScoredTable("products", 1.0, ["注释命中"])]

    def sim(query, text):
        return 1.0 if "products" in text else 0.0

    out = rerank_with_embeddings("均价", cands, idx, sim, weight=2.0)
    assert [c.table for c in out] == ["products", "sales"]
    assert out[0].score == 3.0  # 1.0 + 2.0*1.0


def test_embed_sim_error_falls_back_to_zero():
    idx = _index()
    cands = [ScoredTable("sales", 3.0, [])]

    def bad(q, t):
        raise TypeError("embed 不可用")

    out = rerank_with_embeddings("q", cands, idx, bad, weight=1.0)
    # 相似度异常 → 记为 0，不拉崩重排
    assert out[0].score == 3.0


def test_stable_sort_on_tie():
    idx = _index()
    cands = [ScoredTable("products", 1.0, []), ScoredTable("sales", 1.0, [])]
    out = rerank_with_embeddings("q", cands, idx, lambda q, t: 0.5, weight=2.0)
    # 同分按表名字母序稳定
    assert [c.table for c in out] == ["products", "sales"]


def test_rank_relevant_tables_default_unchanged():
    # 默认（不传 embed）时 rank_relevant_tables 语义与之前一致
    idx = _index()
    got = rank_relevant_tables("各地区销售总额", idx, max_tables=3)
    tables = [c.table for c in got]
    assert "sales" in tables


def test_config_default_disabled():
    from config.settings import get_settings
    assert get_settings().schema_embed_enabled is False
    assert get_settings().schema_embed_fn is None
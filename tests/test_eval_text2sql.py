"""
Text2SQL 相关表检索的单测（确定性、不触库）。

相关表排序/命中 已是 eval/run_eval.py 的 schema_linking 场景覆盖，
这里保留几个轻量单测：核心业务词（订单/销售）必须能命中对应表，
且「订单金额」类查询应把 orders 排在 sales 之前（回归排序稳定）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from core.database.schema_linking import rank_relevant_tables
from eval.run_eval import build_test_index

IDX = build_test_index()


def test_revenue_links_sales():
    ranked = rank_relevant_tables("查询各地区销售总额", IDX, max_tables=3)
    assert ranked and ranked[0].table == "sales"


def test_order_links_orders():
    # 回归：合成索引必须带同义词，否则「订单」这种核心业务词会漏命中（曾踩过的假评测）
    ranked = rank_relevant_tables("今年订单总数", IDX, max_tables=3)
    assert ranked and any(r.table == "orders" for r in ranked)


def test_order_amount_ranks_orders_before_sales():
    ranked = [r.table for r in rank_relevant_tables("今年各地区的总订单金额", IDX, max_tables=3)]
    assert "orders" in ranked
    assert ranked.index("orders") < ranked.index("sales")
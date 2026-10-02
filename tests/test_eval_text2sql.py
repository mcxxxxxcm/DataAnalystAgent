"""
Text2SQL 回归评估的 pytest 包装。

将 eval/golden_queries.json 的确定性回归纳入测试套件，
保证 schema 检索排序与安全拦截不因改动而退化。
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")


def _load_golden() -> list:
    path = Path(__file__).resolve().parent.parent / "eval" / "golden_queries.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_eval_golden_suite_passes():
    from eval.run_eval import _evaluate
    result = _evaluate(_load_golden())
    cases = result["cases"]
    assert cases["fail"] == 0, f"golden suite 有 {cases['fail']} 项失败: {result['details']}"


def test_schema_link_ranks_sales_for_revenue():
    from core.database.schema_linking import TableIndex, rank_relevant_tables, build_synonym_map
    idx = TableIndex()
    synonyms = build_synonym_map()
    idx.add("sales", [{"name": "revenue", "comment": "销售额"}], "销售表", synonyms=synonyms)
    idx.add("products", [{"name": "price", "comment": "价格"}], "产品表", synonyms=synonyms)
    ranked = rank_relevant_tables("查询各地区销售总额", idx, max_tables=3)
    assert ranked[0].table == "sales"
    assert any("销售" in r for r in ranked[0].reasons)
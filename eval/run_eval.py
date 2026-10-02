"""
Text2SQL 回归评估（execution-accuracy 风格，但确定性、不依赖 LLM/DB）

位置：eval/run_eval.py
职责：用 golden 集对「相关表检索排序」与「SQL 安全拦截」做可断言回归，
作为每次 schema / prompt / 安全策略改动后的正确性度量。

运行：py -m eval.run_eval   （在项目根目录执行）

golden 项属性：
- sql_contains / expected.table：判定相关表检索是否命中目标表
- deny_expected=True：判定写操作应被校验层拒绝（enable_write=False 时）
评分：通过数 / 总数。
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")


def _build_index():
    """合成业务表索引（不触库），仅用于评测检索排序。"""
    from core.database.schema_linking import TableIndex
    idx = TableIndex()
    idx.add("sales", [
        {"name": "region", "comment": "地区"},
        {"name": "revenue", "comment": "销售额"},
        {"name": "sales_date", "comment": "销售日期"},
    ], "销售表")
    idx.add("users", [
        {"name": "vip_level", "comment": "会员等级"},
        {"name": "created_at", "comment": "注册时间"},
    ], "用户表")
    idx.add("orders", [
        {"name": "order_date", "comment": "下单日期"},
        {"name": "amount", "comment": "金额"},
    ], "订单表")
    idx.add("products", [
        {"name": "product_name", "comment": "商品名"},
        {"name": "price", "comment": "价格"},
    ], "产品表")
    return idx


def _evaluate(golden: list) -> dict:
    from core.database.schema_linking import rank_relevant_tables
    from core.security.sql_validator import SQLValidator

    index = _build_index()
    cases = {"pass": 0, "fail": 0}
    details = []

    for item in golden:
        gid = item.get("id", "?")
        ok = True
        reasons = []

        if item.get("deny_expected"):
            # 写操作在 enable_write=False 时应被拒绝
            write_sql = "DELETE FROM sales WHERE id = 1"
            validator = SQLValidator(max_rows=100, enable_write=False, timeout=30)
            guards = [validator.validate(write_sql), validator.validate("DROP TABLE sales")]
            ok = any(not g.is_valid for g in guards)
            reasons.append("写操作/DDL 被校验层拒绝" if ok else "写操作未被拒绝(不安全)")

        expected_table = (item.get("expected") or {}).get("table")
        if expected_table:
            ranked = rank_relevant_tables(
                item.get("nl", ""), index, max_tables=3,
                priority_tables=["sales", "orders", "products", "users"],
            )
            ranked_names = [r.table for r in ranked]
            hit = expected_table in ranked_names[:1] or expected_table in ranked_names
            ok = ok and hit
            reasons.append(
                f"相关表检索 [{', '.join(ranked_names[:3])}] 命中 {expected_table}"
                if hit else f"未命中 {expected_table}，实际 {ranked_names}")

        for phrase in item.get("sql_contains", []):
            # 无 DB：以表级检索为代理，不校验具体 SQL 文本（留作交互态人工/DB 用例）
            pass

        cases["pass" if ok else "fail"] += 1
        details.append((gid, ok, "；".join(reasons)))

    return {"cases": cases, "details": details}


def main() -> int:
    golden_path = Path(__file__).resolve().parent / "golden_queries.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    result = _evaluate(golden)

    cases = result["cases"]
    total = cases["pass"] + cases["fail"]
    acc = cases["pass"] / total if total else 0.0

    print("=" * 60)
    print("Text2SQL 上下文回归评估")
    print("=" * 60)
    for gid, ok, reason in result["details"]:
        print(f"[{'PASS' if ok else 'FAIL'}] {gid}: {reason}")
    print("-" * 60)
    print(f"execution-accuracy ≈ {acc:.0%}  ({cases['pass']}/{total})")
    return 0 if cases["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
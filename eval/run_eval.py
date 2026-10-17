"""
Text2SQL 确定性回归评估（多场景聚合 harness）

位置：eval/run_eval.py
职责：对 eval/cases/ 下三类结构化语料做确定性、无 DB / 无 LLM 的断言回归，
作为 schema / 安全 / 路由改动后的正确性度量，任一失败即非零退出（可进 pytest/CI）。

三类 scenario：
- schema_linking : NL → 期望相关表是否命中 top-K（表检索 precision@K）。
- security_deny  : SQL → 应拒的写操作/DDL/堆叠注入被校验层拒绝；控制组合法 SELECT 放行。
- routing_guard  : NL → 意图路由器 verdict 与期望类别一致，且 deny/clarify 语义正确
                   （拒绝类必 deny、歧义必 clarify、放行类两不为真）。

硬门槛：安全 / 路由「该拒必拒、误放行=0」。任一 FAIL → 返回 1。

运行：py -m eval.run_eval    （项目根目录执行）
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from core.database.schema_linking import TableIndex, build_synonym_map, rank_relevant_tables
from core.security.sql_validator import SQLValidator
from core.security.intent_guard import classify_intent, Intent

CASES_DIR = Path(__file__).resolve().parent / "cases"


# ── 合成测试索引（贴近生产：带同义词表） ─────────────────
def build_test_index() -> TableIndex:
    """合成业务表索引（不触库），与生产 get_relevant_schemas 一致地带上同义词。"""
    syn = build_synonym_map()
    idx = TableIndex()
    idx.add("sales", [
        {"name": "region", "comment": "地区"},
        {"name": "revenue", "comment": "销售额"},
        {"name": "sales_date", "comment": "销售日期"},
    ], "销售表", synonyms=syn)
    idx.add("users", [
        {"name": "vip_level", "comment": "会员等级"},
        {"name": "created_at", "comment": "注册时间"},
    ], "用户表", synonyms=syn)
    idx.add("orders", [
        {"name": "order_date", "comment": "下单日期"},
        {"name": "amount", "comment": "金额"},
    ], "订单表", synonyms=syn)
    idx.add("products", [
        {"name": "product_name", "comment": "商品名"},
        {"name": "price", "comment": "价格"},
    ], "产品表", synonyms=syn)
    return idx


@dataclass
class CaseResult:
    gid: str
    scenario: str
    ok: bool
    reason: str


@dataclass
class SuiteSummary:
    cases: dict = field(default_factory=lambda: {"pass": 0, "fail": 0})
    details: list = field(default_factory=list)
    totals: dict = field(default_factory=lambda: {"schema_linking": 0, "security_deny": 0, "routing_guard": 0})


def _load_case_files() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            cases.extend(data)
    return cases


def _routing_deny_expect(category: str) -> dict:
    """URL:由类别推导 deny/clarify 的应然布尔值，避免用例重复写布尔。"""
    if category in {Intent.MALICIOUS.value, Intent.SMALLTALK.value, Intent.OUT_OF_SCOPE.value}:
        return {"deny": True, "clarify": False}
    if category == Intent.AMBIGUOUS.value:
        return {"deny": False, "clarify": True}
    return {"deny": False, "clarify": False}


def evaluate_case(case: dict, index: TableIndex, validator: SQLValidator) -> CaseResult:
    gid = case.get("id", "?")
    scenario = case.get("scenario", "")
    reasons: list[str] = []

    if scenario == "schema_linking":
        nl = case.get("nl", "")
        expected = case.get("expected", [])
        ranked = rank_relevant_tables(nl, index, max_tables=3)
        got = [r.table for r in ranked]
        missing = [t for t in expected if t not in got]
        ok = not missing
        reasons.append(
            f"检索[{', '.join(got) or '无'}] 命中期望 {expected}"
            if ok else f"缺 {missing}（实际 {got}）")

    elif scenario == "security_deny":
        sql = case.get("sql", "")
        deny_expected = bool(case.get("deny_expected", False))
        result = validator.validate(sql)
        rejected = not result.is_valid
        ok = rejected == deny_expected
        reasons.append(
            f"{'拒绝' if rejected else '放行'} {sql[:40]}"
            + (f"（{result.error_type.value}）" if rejected and result.error_type else "")
            if ok else
            f"期望{'拒绝' if deny_expected else '放行'}，实际{'放行' if rejected==False else '拒绝'}")

    elif scenario == "routing_guard":
        nl = case.get("nl", "")
        exp_cat = case.get("expected_category", "")
        verdict = classify_intent(nl, index)
        exp = _routing_deny_expect(exp_cat)
        cat_ok = verdict.category.value == exp_cat
        deny_ok = verdict.deny == exp["deny"]
        clarify_ok = verdict.clarify == exp["clarify"]
        ok = cat_ok and deny_ok and clarify_ok
        reasons.append(f"期望 {exp_cat}/deny={exp['deny']}/clarify={exp['clarify']}，"
                       f"实际 {verdict.category.value}/deny={verdict.deny}/clarify={verdict.clarify}")

    else:
        ok = False
        reasons.append(f"未知 scenario: {scenario}")

    return CaseResult(gid=gid, scenario=scenario, ok=ok, reason="；".join(reasons) or "?")


def run_suite(cases: list[dict], index: TableIndex, validator: SQLValidator) -> SuiteSummary:
    summary = SuiteSummary()
    for case in cases:
        res = evaluate_case(case, index, validator)
        summary.totals[res.scenario] = summary.totals.get(res.scenario, 0) + 1
        summary.cases["pass" if res.ok else "fail"] += 1
        summary.details.append(res)
    return summary


def _format_report(summary: SuiteSummary) -> str:
    lines = ["=" * 62, "Text2SQL 确定性回归评估", "=" * 62]
    for res in summary.details:
        mark = "PASS" if res.ok else "FAIL"
        lines.append(f"[{mark}] ({res.scenario}) {res.gid}: {res.reason}")
    lines.append("-" * 62)
    c = summary.cases
    total = c["pass"] + c["fail"]
    acc = c["pass"] / total if total else 0.0
    lines.append(f"总通过率 ≈ {acc:.0%}  ({c['pass']}/{total})")
    lines.append(f"  按类: " + ", ".join(f"{k}={v}" for k, v in summary.totals.items() if v))
    return "\n".join(lines)


def main() -> int:
    cases = _load_case_files()
    index = build_test_index()
    validator = SQLValidator(max_rows=100, enable_write=False, timeout=30)
    summary = run_suite(cases, index, validator)
    print(_format_report(summary))
    return 0 if summary.cases["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
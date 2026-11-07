"""
坏 case 挖掘工具(半自动)

位置：eval/mine_badcases.py
职责：扫描 logs/tool_calls.jsonl，把「执行失败 / 异常」或「高频可疑」的真实调用 dump 出来，
供人工审阅后沉淀成 eval/cases/ 里的新 case。

运行：py -m eval.mine_badcases [--top 20]
      py -m eval.mine_badcases --sink-security [--apply]   # 把被校验层拒绝的写/注入类失败沉淀进 security_deny.json

注意：这是「发现辅助」，默认不做自动写入（dry-run 打印拟新增）；加 --apply 才真落库。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "tool_calls.jsonl"

# 校验/安全策略拒绝的 error 特征（query_database 被 guard_query_sql / RiskAssessor 拒时）
_SELECT_ERROR_HINTS = ("校验失败", "安全策略拒绝", "deny", "denied", "reject", "禁止", "不允许")


def _norm_sql(sql: str) -> str:
    """幂等去重 key：归一空白 + 大写（去尾分号）。"""
    return re.sub(r"\s+", " ", str(sql or "").strip()).upper().rstrip(";")


def _is_security_reject_error(message: str) -> bool:
    m = (str(message) or "").lower()
    return any(hint in m for hint in _SELECT_ERROR_HINTS)


def _sink_path() -> Path:
    return ROOT / "eval" / "cases" / "security_deny.json"


def propose_security_denies(
    records: list[dict], existing_sqls: list[str], limit: int = 200
) -> list[dict]:
    """把「query_database 被校验/安全层拒绝」的失败调用沉淀成 security_deny 用例。

    纯函数：按规范化 SQL 去重（幂等），跳过已在 existing_sqls 中的；只产出 deny_expected=true。
    """
    existing_norm = {_norm_sql(s) for s in existing_sqls}
    seen: set[str] = set()
    out: list[dict] = []
    n = 0
    for r in records:
        if r.get("tool_name") != "query_database":
            continue
        err = r.get("error") or ""
        # 只收「被安全/校验层拒绝」的调用（注入/写操作/安全策略）；普通 SQL 语法错不算（不应标 deny_expected）
        if not _is_security_reject_error(err):
            continue
        sql = (r.get("input_args") or {}).get("query") or ""
        key = _norm_sql(sql)
        if not key or key in existing_norm or key in seen:
            continue
        seen.add(key)
        n += 1
        out.append({
            "id": f"sec-auto-{n}",
            "scenario": "security_deny",
            "sql": sql,
            "deny_expected": True,
            "source": "log",
            "note": "坏case自动沉淀（mine_badcases --sink-security）",
        })
        if len(out) >= limit:
            break
    return out


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def dump_failures(records: list[dict], top: int) -> None:
    """成功=false 或异常条目。"""
    fails = [r for r in records if r.get("error") or r.get("success") is False]
    print(f"执行失败/异常条目：{len(fails)}")
    for r in fails[:top]:
        tool = r.get("tool_name", "?")
        err = (r.get("error") or "")[:160]
        args = json.dumps(r.get("input_args", {}), ensure_ascii=False)[:120]
        print(f"- [{tool}] {args}  ->  {err}")


def dump_frequent(records: list[dict], top: int) -> None:
    """高频调用与高频失败工具，帮找薄弱点。"""
    tools = Counter((r.get("tool_name") or "?") for r in records)
    print("\n高频工具 top10：")
    for t, c in tools.most_common(10):
        print(f"  {t}: {c}")


def sink_security(records: list[dict], apply: bool = False) -> int:
    """把被校验/安全层拒绝的 query_database 失败沉淀成 security_deny 用例。

    默认 dry-run（只打印拟新增）；--apply 才写回 security_deny.json（按 sql 归一去重，幂等）。
    """
    path = _sink_path()
    existing = load_json_list(path)
    existing_sqls = [c.get("sql", "") for c in existing]
    proposed = propose_security_denies(records, existing_sqls)
    print(f"\n拟沉淀 security_deny 用例：{len(proposed)} 条（源 {LOG_PATH} → {path}）")
    for c in proposed[:50]:
        print(f"  + [{c['id']}] {c['sql'][:80]}")
    if proposed and apply:
        existing.extend(proposed)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已写入 {path}（新增 {len(proposed)} 条）")
        return len(proposed)
    if proposed:
        print("（dry-run：加 --apply 才会写入）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--sink-security", action="store_true",
                    help="把被安全层拒绝的失败调用沉淀进 security_deny.json（配置 --apply 才真写入）")
    ap.add_argument("--apply", action="store_true", help="与 --sink-security 同用时真写入语料")
    args = ap.parse_args()
    records = load_records(LOG_PATH)
    print(f"共 {len(records)} 条调用记录，源 {LOG_PATH}")
    if args.sink_security:
        return sink_security(records, apply=args.apply)
    dump_failures(records, args.top)
    dump_frequent(records, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
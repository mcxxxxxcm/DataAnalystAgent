"""
坏 case 挖掘工具(半自动)

位置：eval/mine_badcases.py
职责：扫描 logs/tool_calls.jsonl，把「执行失败 / 异常」或「高频可疑」的真实调用 dump 出来，
供人工审阅后沉淀成 eval/cases/ 里的新 case。

运行：py -m eval.mine_badcases [--top 20]

注意：这是「发现辅助」，不做自动 gating。是否沉淀进评测集由人判断（考虑行为应然、是否代表一类错）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "tool_calls.jsonl"


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    records = load_records(LOG_PATH)
    print(f"共 {len(records)} 条调用记录，源 {LOG_PATH}")
    dump_failures(records, args.top)
    dump_frequent(records, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
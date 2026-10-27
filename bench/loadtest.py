"""
并发压测脚本

位置：bench/loadtest.py
入口：py -m bench.loadtest

用真实 HTTP 打本服务，衡量 QPS / 延迟分位 / 错误率。
- endpoint=health/ping 不触 LLM/DB，衡量 uvicorn 吞吐上限。
- endpoint=query 走真实 Text2SQL 全链路（调 LLM+DB），最贵最慢。

技术：httpx.AsyncClient + asyncio.Semaphore 限流 + time.perf_counter 计时 + statistics 分位。
不依赖 aiohttp/locust（避免新增依赖；项目已含 httpx）。

安全性：
- endpoint=query 启动打印费用/耗时警告。
- --dry-run 只打印计划即退，不发包。
- 通过 --requests 或 --duration 二选一控制总量，防无限压。
"""
import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx


EP_STYLES = {
    "health": {"default_concurrency": 20, "default_timeout": 15, "weighted_cost": 0},
    "ping": {"default_concurrency": 20, "default_timeout": 15, "weighted_cost": 0},
    "query": {"default_concurrency": 5, "default_timeout": 300, "weighted_cost": 1},
}


def _load_query_file(path: str) -> List[str]:
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                lines.append(ln)
    if not lines:
        raise SystemExit(f"--query-file {path} 为空或无有效查询")
    return lines


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bench.loadtest",
        description="并发压测本服务(可压 /query 全链路或轻量端点)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  py -m bench.loadtest --endpoint health --concurrency 50 --requests 500\n  py -m bench.loadtest --endpoint query --concurrency 5 --duration 60 --query '本月销售额是多少'",
    )
    p.add_argument("--endpoint", choices=["health", "ping", "query"], default="health",
                   help="压测端点(默认 health，query 最贵)")
    p.add_argument("--target", default="http://127.0.0.1:8085",
                   help="服务基址，默认 http://127.0.0.1:8085")
    p.add_argument("--concurrency", type=int, default=None,
                   help="并发数(默认: health/ping=20, query=5)")
    p.add_argument("--duration", type=float, default=None,
                   help="压测时长(秒)，与 --requests 二选一，同时给时 --requests 优先")
    p.add_argument("--requests", type=int, default=None,
                   help="请求总数，与 --duration 二选一")
    p.add_argument("--query", default=None, help="仅 endpoint=query：单条自然语言问题")
    p.add_argument("--query-file", default=None,
                   help="仅 endpoint=query：每行一句 NL 的问题文件(与 --query 互斥)")
    p.add_argument("--thread-mode", choices=["unique", "reuse", "per-worker"], default="unique",
                   help="thread_id 策略: unique=每请求新 uuid；reuse=共用同一 thread；per-worker=每并发 worker 固定一个")
    p.add_argument("--token", default=None, help="Bearer Token(或环境变量 API_AUTH_TOKEN)")
    p.add_argument("--timeout", type=float, default=None,
                   help="单请求超时(秒)，默认按端点给")
    p.add_argument("--report-interval", type=float, default=0.0,
                   help="进度打印间隔(秒)，0=关")
    p.add_argument("--json", dest="as_json", action="store_true",
                   help="终结果 JSON 打 stdout")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印执行计划即退，不发包")
    return p


def _resolve(default: Optional[int], given: Optional[int]) -> int:
    return int(given) if given is not None else default


def _print_plan(args: argparse.Namespace) -> None:
    style = EP_STYLES[args.endpoint]
    print("=== 压测计划 bench.loadtest ===")
    print(f"  Endpoint   : {args.endpoint}")
    print(f"  Target     : {args.target}")
    print(f"  Concurrency: {_resolve(style['default_concurrency'], args.concurrency)}")
    if args.requests:
        print(f"  总量        : {args.requests} 请求")
    elif args.duration:
        print(f"  时长        : {args.duration} 秒")
    else:
        print(f"  (未指定总量 → 需 --requests 或 --duration)")
    if args.endpoint == "query":
        src = f"--query '{args.query}'" if args.query else f"--query-file {args.query_file}"
        print(f"  问题        : {src}")
        print(f"  Thread模式 : {args.thread_mode}")
    print("  Dry-run     : 仅打印计划，未发包")


def _make_headers(args: argparse.Namespace) -> Optional[Dict[str, str]]:
    token = args.token or os.environ.get("API_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def _thread_id_for(args: argparse.Namespace, worker_idx: int, request_idx: int) -> str:
    if args.thread_mode == "unique":
        return str(uuid.uuid4())
    if args.thread_mode == "reuse":
        return "bench-reuse"  # 共用同一 thread：累积上下文 + 每轮 checkpoint 写库
    # per-worker：每个并发 worker 固定一个 thread（贴近 N 用户多轮）
    return f"bench-worker-{worker_idx}"


def _summarize(latencies: List[float]) -> Dict[str, float]:
    if not latencies:
        return {}
    lat = sorted(latencies)
    q = lambda pct: statistics.quantiles(lat, n=100)[pct - 1] if len(lat) >= 100 else lat[
        int(pct / 100 * (len(lat) - 1))]
    return {
        "mean": round(statistics.mean(lat), 3),
        "p50": round(q(50), 3),
        "p90": round(q(90), 3),
        "p95": round(q(95), 3),
        "p99": round(q(99), 3),
        "max": round(lat[-1], 3),
    }


async def _send_one(client: httpx.AsyncClient, args: argparse.Namespace,
                    worker_idx: int, request_idx: int) -> tuple[bool, str, float]:
    """发单个请求，返回 (是否记入成功但非错误, 结果语义, 延迟秒)。"""
    start = time.perf_counter()
    headers = _make_headers(args)
    if args.endpoint == "health":
        r = await client.get(f"{args.target}/api/health", headers=headers)
        return r.status_code == 200, "ok", time.perf_counter() - start
    if args.endpoint == "ping":
        r = await client.get(f"{args.target}/api/stats", headers=headers)
        return r.status_code == 200, "ok", time.perf_counter() - start
    # query
    query = args.query or ""
    payload = {"query": query, "thread_id": _thread_id_for(args, worker_idx, request_idx)}
    r = await client.post(f"{args.target}/api/query", json=payload, headers=headers)
    if r.status_code != 200:
        return False, f"http_{r.status_code}", time.perf_counter() - start
    try:
        body = r.json()
    except Exception:
        return False, "bad_json", time.perf_counter() - start
    if body.get("requires_approval"):
        return True, "hitl", time.perf_counter() - start  # 成功但单列
    if body.get("success") is False and body.get("error"):
        return False, "llm_fail", time.perf_counter() - start
    return True, "ok", time.perf_counter() - start


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    style = EP_STYLES[args.endpoint]
    concurrency = _resolve(style["default_concurrency"], args.concurrency)
    timeout = _resolve(style["default_timeout"], args.timeout)

    # 总量确定
    if args.requests:
        total = args.requests
    elif args.duration:
        total = int(concurrency * args.duration * 100)  # 保守上限，由时长提前中断
    else:
        raise SystemExit("必须提供 --requests 或 --duration 之一")

    sem = asyncio.Semaphore(concurrency)
    latencies: List[float] = []
    breakdown: Dict[str, int] = {}
    success_count = 0
    error_count = 0
    hitl_count = 0
    sent = 0
    start_all = time.perf_counter()
    time_limit = start_all + (args.duration if args.duration else float("inf"))

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def _worker(worker_idx: int):
            nonlocal sent, success_count, error_count, hitl_count
            request_idx = 0
            while True:
                if args.requests and sent >= args.requests:
                    break
                if time.perf_counter() > time_limit:
                    break
                async with sem:
                    ok_flag, status, dt = await _send_one(client, args, worker_idx, request_idx)
                    request_idx += 1
                    sent += 1
                    latencies.append(dt)
                    breakdown[status] = breakdown.get(status, 0) + 1
                    if status == "hitl":
                        hitl_count += 1
                        success_count += 1
                    elif ok_flag:
                        success_count += 1
                    else:
                        error_count += 1

        workers = [asyncio.create_task(_worker(i)) for i in range(concurrency)]
        await asyncio.gather(*workers)

    duration = time.perf_counter() - start_all
    qps = sent / duration if duration > 0 else 0.0
    return {
        "endpoint": args.endpoint,
        "target": args.target,
        "concurrency": concurrency,
        "requests_total": total,
        "requests_completed": sent,
        "duration_seconds": round(duration, 3),
        "qps": round(qps, 3),
        "latency": _summarize(latencies),
        "success_count": success_count,
        "error_count": error_count,
        "error_rate": round(error_count / sent, 4) if sent else 0.0,
        "breakdown": breakdown,
        "hitl_count": hitl_count,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.endpoint == "query":
        if args.query and args.query_file:
            raise SystemExit("--query 与 --query-file 互斥，只能二选一")
        if not (args.query or args.query_file):
            raise SystemExit("endpoint=query 必须提供 --query 或 --query-file")
        if args.query_file:
            # 简化：query-file 仅支持 unique 模式，逐条轮询
            args._query_list = _load_query_file(args.query_file)
    else:
        args._query_list = None

    if not args.requests and not args.duration:
        raise SystemExit("必须提供 --requests 或 --duration 之一")

    _print_plan(args)
    if args.endpoint == "query":
        print("\n警告：endpoint=query 会真实调用 LLM(有 token 费用)与数据库(有查询开销)，耗时通常数秒/请求。")
        print("      建议先 --dry-run 及小 --requests 验证，或用 --endpoint health 先做框架吞吐基线。")
    if args.dry_run:
        return

    if args.endpoint == "query" and args._query_list:
        print("提示：--query-file 仅支持复试，将在 unique 模式下逐条轮询。")

    result = asyncio.run(_run(args))
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    print("\n=== 压测报告 bench.loadtest ===")
    print(f"  Endpoint     : {result['endpoint']}")
    print(f"  Target       : {result['target']}")
    print(f"  Concurrency  : {result['concurrency']}")
    print(f"  Requests     : {result['requests_completed']} / {result['requests_total']}")
    print(f"  Duration     : {result['duration_seconds']} s")
    print(f"  QPS          : {result['qps']} req/s")
    lat = result["latency"]
    if lat:
        print(f"  Latency(ms)  : mean={lat['mean']*1000:.0f} p50={lat['p50']*1000:.0f} "
              f"p90={lat['p90']*1000:.0f} p95={lat['p95']*1000:.0f} p99={lat['p99']*1000:.0f} "
              f"max={lat['max']*1000:.0f}")
    print(f"  Success      : {result['success_count']} ({result['success_count']/max(result['requests_completed'],1)*100:.1f}%)")
    print(f"  Errors       : {result['error_count']} ({result['error_rate']*100:.1f}%)")
    print(f"  Breakdown    : {result['breakdown']}")
    if result['endpoint'] == 'query':
        print(f"  HITL interrupts: {result['hitl_count']}")


if __name__ == "__main__":
    main()
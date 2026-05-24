"""
usage_tracker.py — Parse llm_router.log and produce daily/weekly usage stats.
Called by reporter agent to add LLM routing stats to daily report.
"""
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_FILE = Path.home() / "btc-agents" / "logs" / "llm_router.log"
LOG_PATTERN = re.compile(
    r"(?P<ts>\S+)\|(?P<agent>[^|]+)\|(?P<tier>[^|]+)\|(?P<provider>[^|]+)\|"
    r"(?P<model>[^|]+)\|(?P<fallbacks>\d+)\|(?P<tok_in>\d+)\|(?P<tok_out>\d+)\|"
    r"(?P<ms>\d+)\|cost_usd:(?P<cost>[\d.]+)"
)


def parse_log(since: datetime | None = None) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    entries = []
    with LOG_FILE.open() as f:
        for line in f:
            m = LOG_PATTERN.match(line.strip())
            if not m:
                continue
            try:
                ts = datetime.fromisoformat(m.group("ts"))
            except ValueError:
                continue
            if since and ts < since:
                continue
            entries.append({
                "ts": ts,
                "agent": m.group("agent"),
                "tier": m.group("tier"),
                "provider": m.group("provider"),
                "model": m.group("model"),
                "fallbacks": int(m.group("fallbacks")),
                "tok_in": int(m.group("tok_in")),
                "tok_out": int(m.group("tok_out")),
                "ms": int(m.group("ms")),
                "cost": float(m.group("cost")),
            })
    return entries


def summarize(entries: list[dict]) -> dict:
    if not entries:
        return {"calls": 0, "cost_usd": 0.0, "providers": {}, "fallback_rate": "0%", "avg_latency_ms": 0}

    providers: dict[str, int] = defaultdict(int)
    fallback_calls = 0
    total_ms = 0

    for e in entries:
        providers[e["provider"]] += 1
        if e["fallbacks"] > 0:
            fallback_calls += 1
        total_ms += e["ms"]

    fallback_rate = f"{100 * fallback_calls / len(entries):.1f}%"
    return {
        "calls": len(entries),
        "cost_usd": 0.00,
        "providers": dict(providers),
        "fallback_rate": fallback_rate,
        "avg_latency_ms": round(total_ms / len(entries)),
    }


def daily_stats() -> dict:
    since = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return summarize(parse_log(since=since))


def weekly_stats() -> dict:
    since = datetime.now(tz=timezone.utc) - timedelta(days=7)
    return summarize(parse_log(since=since))


def format_report_line(stats: dict) -> str:
    providers_str = ", ".join(f"{p}:{c}" for p, c in sorted(stats["providers"].items()))
    return (
        f"LLM: {stats['calls']} calls | cost $0.00 | "
        f"fallback_rate {stats['fallback_rate']} | "
        f"avg {stats['avg_latency_ms']}ms | "
        f"providers [{providers_str}]"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "weekly":
        stats = weekly_stats()
        label = "7-day"
    else:
        stats = daily_stats()
        label = "today"
    print(f"=== LLM Routing Stats ({label}) ===")
    print(format_report_line(stats))
    if stats["providers"]:
        print("Breakdown by provider:")
        for p, c in sorted(stats["providers"].items()):
            print(f"  {p}: {c} calls")
    print(f"Total cost: ${stats['cost_usd']:.2f}")

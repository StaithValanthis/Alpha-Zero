"""
usage_tracker.py — Parse llm_router.log and produce daily/weekly pool health stats.
Writes logs/daily_usage/YYYY-MM-DD.json. Called by reporter for Discord stats line.
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_FILE    = Path.home() / "btc-agents" / "logs" / "llm_router.log"
USAGE_DIR   = Path.home() / "btc-agents" / "logs" / "daily_usage"
USAGE_DIR.mkdir(parents=True, exist_ok=True)

LOG_PAT = re.compile(
    r"(?P<ts>\S+)\|(?P<agent>[^|]+)\|(?P<tier>[^|]+)\|(?P<provider>[^|]+)\|"
    r"(?P<model>[^|]+)\|(?P<fallbacks>\d+)\|(?P<tok_in>\d+)\|(?P<tok_out>\d+)\|"
    r"(?P<ms>\d+)\|cost_usd:(?P<cost>[\d.]+)"
)

# Pool classification
_MODEL_TO_POOL = {
    "qwen-3-235b-a22b-instruct-2507": "cerebras_pool",
    "gpt-oss-120b":                   "groq_gpt-oss-120b",
    "openai/gpt-oss-120b":            "groq_gpt-oss-120b",
    "llama-3.3-70b-versatile":        "groq_llama-3.3-70b",
    "meta-llama/llama-4-scout-17b-16e-instruct": "groq_llama-4-scout",
    "llama-3.1-8b-instant":           "groq_llama-3.1-8b",
    "gemini-2.0-flash":               "gemini",
}

CEREBRAS_TOK_DAY_BUDGET = 1_000_000


def _pool(provider: str, model: str) -> str:
    if provider in ("mistral",):
        return "mistral"
    if provider == "openrouter":
        return "openrouter"
    if provider == "gemini":
        return "gemini"
    # Groq / Cerebras — look up by model suffix
    for key, pool in _MODEL_TO_POOL.items():
        if model.endswith(key) or model == key:
            return pool
    return f"{provider}_other"


def parse_log(since: datetime | None = None) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    rows = []
    with LOG_FILE.open() as f:
        for line in f:
            m = LOG_PAT.match(line.strip())
            if not m:
                continue
            try:
                ts = datetime.fromisoformat(m.group("ts").replace("Z", "+00:00"))
            except ValueError:
                continue
            if since and ts < since:
                continue
            rows.append({
                "ts":        ts,
                "agent":     m.group("agent"),
                "tier":      m.group("tier"),
                "provider":  m.group("provider"),
                "model":     m.group("model"),
                "fallbacks": int(m.group("fallbacks")),
                "tok_in":    int(m.group("tok_in")),
                "tok_out":   int(m.group("tok_out")),
                "ms":        int(m.group("ms")),
                "cost":      float(m.group("cost")),
            })
    return rows


def summarize(rows: list[dict], date_str: str) -> dict:
    pool_stats: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_used": 0, "fallback_count": 0
    })
    tier_calls: dict[str, int] = defaultdict(int)
    tier_primary_hits: dict[str, int] = defaultdict(int)

    for r in rows:
        p = _pool(r["provider"], r["model"])
        pool_stats[p]["calls"] += 1
        pool_stats[p]["tokens_used"] += r["tok_in"] + r["tok_out"]
        if r["fallbacks"] > 0:
            pool_stats[p]["fallback_count"] += 1
        tier_calls[r["tier"]] += 1
        if r["fallbacks"] == 0:
            tier_primary_hits[r["tier"]] += 1

    # Cerebras budget
    cb = pool_stats.get("cerebras_pool", {})
    if cb:
        cb["daily_budget_remaining"] = CEREBRAS_TOK_DAY_BUDGET - cb["tokens_used"]
        cb["pct_used"] = round(100 * cb["tokens_used"] / CEREBRAS_TOK_DAY_BUDGET, 1)

    by_tier = {}
    for tier, calls in tier_calls.items():
        hits = tier_primary_hits.get(tier, 0)
        by_tier[tier] = {
            "calls": calls,
            "primary_hit_rate_pct": round(100 * hits / calls, 1) if calls else 0.0,
        }

    alerts = []
    # Cerebras budget alert
    if cb.get("pct_used", 0) > 80:
        alerts.append(f"CEREBRAS BUDGET: {cb['pct_used']}% of 1M daily tokens used")
    # Primary hit rate
    for tier, stats in by_tier.items():
        if stats["primary_hit_rate_pct"] < 70:
            alerts.append(
                f"TIER {tier}: primary hit rate {stats['primary_hit_rate_pct']}% < 70%")
    # Mistral fallback rate
    mistral_calls = pool_stats.get("mistral", {}).get("calls", 0)
    total_calls = sum(s["calls"] for s in pool_stats.values())
    if total_calls and mistral_calls / total_calls > 0.10:
        alerts.append(
            f"MISTRAL FALLBACK: {mistral_calls}/{total_calls} calls "
            f"({100*mistral_calls/total_calls:.1f}%) — primary pools saturated")
    # OpenRouter fallback rate
    or_calls = pool_stats.get("openrouter", {}).get("calls", 0)
    if total_calls and or_calls / total_calls > 0.05:
        alerts.append(
            f"OPENROUTER FALLBACK: {or_calls}/{total_calls} calls "
            f"({100*or_calls/total_calls:.1f}%) — last resort triggered too often")

    return {
        "date": date_str,
        "total_cost_usd": 0.00,
        "total_calls": total_calls,
        "by_provider_pool": {k: dict(v) for k, v in pool_stats.items()},
        "by_tier": by_tier,
        "alerts": alerts,
    }


def daily_summary(date: datetime | None = None) -> dict:
    if date is None:
        date = datetime.now(tz=timezone.utc)
    since = date.replace(hour=0, minute=0, second=0, microsecond=0)
    date_str = since.strftime("%Y-%m-%d")
    rows = parse_log(since=since)
    return summarize(rows, date_str)


def weekly_summary() -> dict:
    since = datetime.now(tz=timezone.utc) - timedelta(days=7)
    date_str = since.strftime("%Y-%m-%d") + "_7d"
    rows = parse_log(since=since)
    return summarize(rows, date_str)


def discord_line(stats: dict) -> str:
    pp = stats["by_provider_pool"]
    def c(pool): return pp.get(pool, {}).get("calls", 0)

    cerebras = c("cerebras_pool")
    cb_pct   = pp.get("cerebras_pool", {}).get("pct_used", 0.0)
    g70      = c("groq_llama-3.3-70b")
    goss     = c("groq_gpt-oss-120b")
    scout    = c("groq_llama-4-scout")
    g8b      = c("groq_llama-3.1-8b")
    mistral  = c("mistral")
    gemini   = c("gemini")
    openr    = c("openrouter")

    total    = stats["total_calls"]
    primary_hits = sum(
        v["calls"] for v in stats["by_tier"].values()
        if v["primary_hit_rate_pct"] >= 70
    )
    tiers    = len(stats["by_tier"])
    hit_rate = round(100 * primary_hits / tiers, 1) if tiers else 0

    alerts = f" | ⚠️ {len(stats['alerts'])} alert(s)" if stats["alerts"] else ""
    return (
        f"🔀 LLM routing today: Cerebras {cerebras} calls ({cb_pct}% daily budget) | "
        f"Groq: 70b {g70} | gpt-oss {goss} | scout {scout} | 8b {g8b} | "
        f"Mistral: {mistral} | Gemini: {gemini} | OpenRouter: {openr} | "
        f"Primary hit rate: {hit_rate}% | Total cost: $0.00{alerts}"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "weekly":
        stats = weekly_summary()
    else:
        stats = daily_summary()

    # Write JSON
    out_path = USAGE_DIR / f"{stats['date']}.json"
    out_path.write_text(json.dumps(stats, indent=2))

    print(f"=== LLM Pool Health ({stats['date']}) ===")
    print(f"Total calls: {stats['total_calls']} | Cost: $0.00")
    print()
    print("By pool:")
    for pool, data in sorted(stats["by_provider_pool"].items()):
        fb = data.get("fallback_count", 0)
        tok = data.get("tokens_used", 0)
        extra = ""
        if "cerebras" in pool:
            extra = f" | {data.get('pct_used',0)}% of 1M daily budget"
        print(f"  {pool:<30} calls:{data['calls']:<4} tok:{tok:<8} fallbacks:{fb}{extra}")
    print()
    print("By tier (primary hit rate):")
    for tier, data in sorted(stats["by_tier"].items()):
        print(f"  {tier:<22} calls:{data['calls']:<4} primary:{data['primary_hit_rate_pct']}%")
    if stats["alerts"]:
        print()
        print("ALERTS:")
        for a in stats["alerts"]:
            print(f"  ! {a}")
    else:
        print("\nNo alerts.")
    print()
    print(discord_line(stats))
    print(f"\nWritten: {out_path}")

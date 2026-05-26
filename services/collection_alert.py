#!/usr/bin/env python3
"""
Collection Degradation Alerter — no-LLM watchdog.

Reads data/meta/collection_status.json every 15 min (via Hermes cron).
Prints nothing on clean runs — Hermes stays silent (no_agent silent pattern).
Prints an alert to stdout when any collector is degraded — Hermes delivers verbatim to Discord.

Schema (from collection_monitor.py):
  health               — overall: green | yellow | red
  file_health          — mtime-based
  content_health       — fingerprint + data_count based
  age_seconds          — mtime age
  content_unchanged_seconds — seconds since content hash last changed
  data_count           — len(data[]) for envelope files, -1 if not applicable

Catches three failure modes:
  1. health=red: mtime stale OR data empty (data_count==0) OR content frozen past threshold
  2. health=yellow: aging — worth flagging so action can be taken before red
  3. content_unchanged_seconds growing on a high-frequency collector (degraded-but-writing)
"""
import json, os, sys
from datetime import datetime, timezone

BASE = os.path.expanduser('~/btc-agents')
STATUS_FILE = f'{BASE}/data/meta/collection_status.json'

# Collectors expected to have new content on every run.
# If content_unchanged_seconds exceeds this while file_health=green,
# the source is writing without new data (paywalled/degraded).
# Keyed to each collector's normal update cadence * 6 (generous buffer).
CONTENT_STALE_WARN = {
    'btc_candles':     360  * 6,     # candles every 5min — warn after 30min frozen
    'ta_engine':       400  * 6,     # TA every ~5min — warn after 40min frozen
    'news':            3600,         # warn after 1h of frozen content (was 10800 — too loose)
    'news_classified': 3600,         # same
    'derivatives':     3600 * 6,     # derivatives every 60min — warn after 6h frozen
    'whales':          3600 * 6,
    'netflow':         8000 * 6,
    'options':         4000 * 6,
    'onchain':         90000,        # daily — 25h before we care
    'fear_greed':      90000,        # daily
    'etf_flows':       50000 * 2,    # ~14h — allow two cycles before flagging
    'alt_watchlist':   90000,        # daily
}

# Human-readable thresholds for newest_record_age alerts (in seconds)
SEMANTIC_STALE_WARN = {
    'news':            6 * 3600,
    'news_classified': 6 * 3600,
    'netflow':         36 * 3600,
    'etf_flows':       48 * 3600,
    'fear_greed':      30 * 3600,
    'whales':          4 * 3600,
}


def main():
    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
    except FileNotFoundError:
        print(f"COLLECTION ALERT: {STATUS_FILE} not found — is collection_monitor.service running?")
        sys.exit(0)
    except Exception as e:
        print(f"COLLECTION ALERT: cannot read status file: {e}")
        sys.exit(0)

    checked_at = status.get('checked_at', 'unknown')
    collectors = status.get('collectors', {})
    problems = []

    for name, info in collectors.items():
        health = info.get('health', 'unknown')
        file_health = info.get('file_health', 'unknown')
        content_health = info.get('content_health', 'unknown')
        age = info.get('age_seconds', -1)
        unchanged = info.get('content_unchanged_seconds', -1)
        data_count = info.get('data_count', -1)
        newest_record_age = info.get('newest_record_age_seconds', -1)
        issues = []

        if health == 'red':
            if file_health == 'red':
                issues.append(f"FILE STALE (mtime {age}s old)")
            if data_count == 0:
                issues.append("DATA EMPTY (0 records — source paywalled or broken)")
            elif content_health == 'red' and data_count != 0:
                h = unchanged // 3600 if unchanged > 0 else 0
                issues.append(f"CONTENT FROZEN ({unchanged}s / ~{h}h unchanged)")
        elif health == 'yellow':
            if file_health == 'yellow':
                issues.append(f"FILE AGING (mtime {age}s)")
            if content_health == 'yellow' and data_count != 0:
                h = unchanged // 3600 if unchanged > 0 else 0
                issues.append(f"CONTENT STAGNATING ({unchanged}s / ~{h}h unchanged)")

        # Semantic record age — surfaced regardless of overall health colour
        # so operator sees "newest article 8h old" even when health is still green
        if newest_record_age > 0 and name in SEMANTIC_STALE_WARN:
            warn_thr = SEMANTIC_STALE_WARN[name]
            if newest_record_age > warn_thr:
                h = newest_record_age // 3600
                severity = "STALE" if newest_record_age > warn_thr * 2 else "AGING"
                issues.append(f"NEWEST RECORD {severity} (~{h}h old — source may be serving stale data)")

        # Degraded-but-writing: file_health=green but content frozen longer than our threshold
        if (
            not issues
            and file_health == 'green'
            and unchanged > 0
            and name in CONTENT_STALE_WARN
            and unchanged > CONTENT_STALE_WARN[name]
        ):
            h = unchanged // 3600
            issues.append(
                f"DEGRADED-BUT-WRITING: file fresh, content frozen {unchanged}s / ~{h}h "
                f"(source rewriting with no new data)"
            )

        if issues:
            problems.append(f"  {name}: " + " | ".join(issues))

    if not problems:
        sys.exit(0)

    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    lines = [
        f"COLLECTION DEGRADATION ALERT — {now_utc}",
        f"(monitor checked_at: {checked_at})",
        "",
        "Degraded collectors:",
    ] + problems + [
        "",
        "Agents are consuming stale or empty data from these sources.",
        "Signals derived from them should be treated with low confidence.",
        "",
        "Triage:",
        "  journalctl -u btc-<name>.service -n 50",
        "  systemctl status btc-<name>.service",
    ]

    print("\n".join(lines))


if __name__ == '__main__':
    main()

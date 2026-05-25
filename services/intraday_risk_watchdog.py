#!/usr/bin/env python3
"""
intraday_risk_watchdog.py — no-LLM flash crash and funding inversion detector.

Runs every 5 min via Hermes cron (no_agent=True).
- Reads ws_prices.json and funding_history.json
- Triggers on: 5-min price drop >= 5%, funding < -0.03%, or 1h cascade >= 8%
- On trigger: sets anomaly_state.json auto_pause_signal_watcher=true,
  POSTs Discord alert, appends system-log.json
- Clears auto_pause when trigger condition gone AND 30 min elapsed
- Silent on clean runs (stdout empty = no Discord delivery)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

B = os.path.expanduser("~/btc-agents")
PRICE_CACHE = os.path.join(B, "state", "watchdog_price_cache.json")
ANOMALY = os.path.join(B, "state", "anomaly_state.json")
SYSLOG = os.path.join(B, "state", "system-log.json")

# Thresholds
FLASH_CRASH_5M_PCT = -5.0   # 5-min drop >= 5%
CASCADE_1H_PCT = -8.0        # 1-hr drop >= 8%
FUNDING_EXTREME = -0.03      # funding rate < -0.03% = extreme negative inversion
CLEAR_HOLD_SECS = 1800       # 30 min hold before auto-clearing


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_env():
    env = {}
    env_path = os.path.join(B, ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def now_utc():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def post_discord(webhook_url, title, description, color=16711680):
    try:
        requests.post(
            webhook_url,
            json={"embeds": [{"title": title, "description": description, "color": color}]},
            timeout=5,
        )
    except Exception:
        pass


def append_syslog(event_type, message):
    syslog = load(SYSLOG, [])
    if isinstance(syslog, list):
        entries = syslog
    else:
        entries = syslog.get("entries", [])
    entries.append({
        "timestamp": now_utc(),
        "event": event_type,
        "message": message,
        "source": "intraday_risk_watchdog",
    })
    # Keep last 500
    entries = entries[-500:]
    atomic_write(SYSLOG, {"last_updated": now_utc(), "entries": entries})


def main():
    env = load_env()
    webhook = env.get("DISCORD_WEBHOOK_URL", "")

    # --- Read current price ---
    ws_prices = load(os.path.join(B, "data", "market", "ws_prices.json"), {})
    current_price = None
    for key in ["BTCUSDT", "BTC/USDT", "btcusdt"]:
        if key in ws_prices:
            val = ws_prices[key]
            current_price = float(val.get("price", val) if isinstance(val, dict) else val)
            break
    if current_price is None:
        # Can't evaluate — exit silently
        sys.exit(0)

    ts_now = time.time()

    # --- Load price cache (rolling window) ---
    cache = load(PRICE_CACHE, {"readings": []})
    readings = cache.get("readings", [])

    # Append current reading
    readings.append({"price": current_price, "ts": ts_now})

    # Trim to last 90 min of readings (5-min ticks = 18 readings)
    cutoff_1h = ts_now - 3600
    readings = [r for r in readings if r["ts"] >= cutoff_1h]
    atomic_write(PRICE_CACHE, {"readings": readings})

    # --- Compute 5-min change ---
    change_5m_pct = None
    cutoff_5m = ts_now - 310  # 5 min + 10s tolerance
    readings_5m = [r for r in readings if r["ts"] <= cutoff_5m]
    if readings_5m:
        price_5m_ago = readings_5m[-1]["price"]
        change_5m_pct = ((current_price - price_5m_ago) / price_5m_ago) * 100

    # --- Compute 1-hr change ---
    change_1h_pct = None
    if len(readings) >= 2:
        price_1h_ago = readings[0]["price"]
        change_1h_pct = ((current_price - price_1h_ago) / price_1h_ago) * 100

    # --- Read funding rate ---
    funding_data = load(os.path.join(B, "data", "market", "funding_history.json"), {})
    funding_rate = None
    # Common schema patterns
    if isinstance(funding_data, dict):
        fr = funding_data.get("funding_rate_latest") or funding_data.get("latest_funding_rate")
        if fr is not None:
            funding_rate = float(fr)
        elif "data" in funding_data and isinstance(funding_data["data"], list) and funding_data["data"]:
            entry = funding_data["data"][-1]
            funding_rate = float(entry.get("fundingRate", entry.get("funding_rate", 0)))

    # --- Evaluate triggers ---
    triggers = []

    if change_5m_pct is not None and change_5m_pct <= FLASH_CRASH_5M_PCT:
        triggers.append({
            "type": "flash_crash",
            "value": round(change_5m_pct, 2),
            "threshold": FLASH_CRASH_5M_PCT,
            "desc": f"5-min price drop {change_5m_pct:.2f}% (threshold {FLASH_CRASH_5M_PCT}%)",
        })

    if change_1h_pct is not None and change_1h_pct <= CASCADE_1H_PCT:
        triggers.append({
            "type": "cascade_risk",
            "value": round(change_1h_pct, 2),
            "threshold": CASCADE_1H_PCT,
            "desc": f"1-hr price drop {change_1h_pct:.2f}% (threshold {CASCADE_1H_PCT}%)",
        })

    if funding_rate is not None and funding_rate < FUNDING_EXTREME:
        triggers.append({
            "type": "funding_inversion",
            "value": round(funding_rate, 5),
            "threshold": FUNDING_EXTREME,
            "desc": f"Funding rate {funding_rate:.4f}% (extreme negative threshold {FUNDING_EXTREME}%)",
        })

    # --- Load current anomaly state ---
    anomaly = load(ANOMALY, {})
    currently_paused = anomaly.get("auto_pause_signal_watcher", False)
    paused_since_str = anomaly.get("watchdog_paused_since")
    paused_since = None
    if paused_since_str:
        try:
            paused_since = datetime.fromisoformat(paused_since_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass

    if triggers:
        # --- Fire: set pause, alert, log ---
        if not currently_paused:
            anomaly["auto_pause_signal_watcher"] = True
            anomaly["watchdog_paused_since"] = now_utc()
            anomaly["current_anomalies"] = [
                {"type": t["type"], "value": t["value"], "detected_at": now_utc()}
                for t in triggers
            ]
            anomaly["active_since"] = now_utc()
            anomaly["expected_clear_condition"] = "Trigger condition resolved AND 30 min hold elapsed"
            anomaly["last_updated"] = now_utc()
            atomic_write(ANOMALY, anomaly)

            desc = "\n".join(f"• {t['desc']}" for t in triggers)
            desc += f"\n\nBTC price: ${current_price:,.0f}\nsignal_watcher paused — no new entries until clear."
            post_discord(webhook, "🚨 RISK ALERT — Signal Watcher Paused", desc, color=16711680)
            append_syslog("watchdog_trigger", f"Triggered: {[t['type'] for t in triggers]}. Price={current_price}")
            print(f"TRIGGERED: {[t['type'] for t in triggers]} — auto_pause_signal_watcher=true")
        else:
            # Already paused — just update anomaly list
            anomaly["current_anomalies"] = [
                {"type": t["type"], "value": t["value"], "detected_at": now_utc()}
                for t in triggers
            ]
            anomaly["last_updated"] = now_utc()
            atomic_write(ANOMALY, anomaly)
            # Silent — already alerted

    else:
        # --- No triggers: check if we should clear ---
        if currently_paused and paused_since:
            elapsed = ts_now - paused_since
            if elapsed >= CLEAR_HOLD_SECS:
                anomaly["auto_pause_signal_watcher"] = False
                anomaly["current_anomalies"] = []
                anomaly["active_since"] = None
                anomaly["watchdog_paused_since"] = None
                anomaly["expected_clear_condition"] = None
                anomaly["last_updated"] = now_utc()
                atomic_write(ANOMALY, anomaly)
                post_discord(webhook, "✅ Risk Watchdog — All Clear",
                             f"Trigger conditions resolved. signal_watcher resumed.\nBTC price: ${current_price:,.0f}",
                             color=65280)
                append_syslog("watchdog_clear", f"Cleared after {elapsed/60:.0f} min hold. Price={current_price}")
                print(f"CLEARED: auto_pause_signal_watcher reset after {elapsed/60:.0f} min")
        # Clean run — silent (empty stdout = no delivery)


if __name__ == "__main__":
    main()

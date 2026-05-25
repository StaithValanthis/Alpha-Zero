#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from statistics import mean

# Load funding history
with open('data/market/funding_history.json', 'r') as f:
    funding_data = json.load(f)

# Load open interest
with open('data/market/open_interest.json', 'r') as f:
    oi_data = json.load(f)

# Load long/short ratio
with open('data/market/long_short_ratio.json', 'r') as f:
    ls_data = json.load(f)

# Extract funding rates
funding_rates = [float(item['fundingRate']) for item in funding_data['data']]

# Latest funding rate
latest_funding = funding_rates[0]

# 7-day average
avg_funding_7d = mean(funding_rates) if len(funding_rates) > 0 else 0

# Funding trend analysis
recent_rates = funding_rates[:5]
older_rates = funding_rates[5:10]
recent_avg = mean(recent_rates) if recent_rates else 0
older_avg = mean(older_rates) if older_rates else 0

if recent_avg > older_avg + 0.000005:
    funding_trend = "rising"
elif recent_avg < older_avg - 0.000005:
    funding_trend = "falling"
else:
    funding_trend = "stable"

# Determine funding regime
latest_funding_pct = latest_funding * 100
if latest_funding_pct < -0.01:
    funding_regime = "extreme_negative"
    funding_signal = "accumulation_signal"
elif latest_funding_pct < -0.003:
    funding_regime = "negative"
    funding_signal = "mild_bullish"
elif latest_funding_pct <= 0.003:
    funding_regime = "neutral"
    funding_signal = "neutral"
elif latest_funding_pct <= 0.015:
    funding_regime = "positive"
    funding_signal = "mild_crowding_caution"
else:
    funding_regime = "extreme_positive"
    funding_signal = "distribution_signal"

# Open Interest analysis
oi_values = [float(item['openInterest']) for item in oi_data['data']]
latest_oi = oi_values[0]
oldest_oi_24h = oi_values[-1] if len(oi_values) > 0 else latest_oi

oi_change_24h = ((latest_oi - oldest_oi_24h) / oldest_oi_24h) * 100 if oldest_oi_24h > 0 else 0

if oi_change_24h > 0.5:
    oi_trend = "expanding"
elif oi_change_24h < -0.5:
    oi_trend = "contracting"
else:
    oi_trend = "flat"

# Long/Short ratio analysis
ls_values = ls_data['data']
latest_buy_ratio = float(ls_values[0]['buyRatio'])
latest_sell_ratio = float(ls_values[0]['sellRatio'])
long_short_ratio = latest_buy_ratio / latest_sell_ratio if latest_sell_ratio > 0 else 1

# Determine bias
if latest_buy_ratio > 0.545:
    long_short_bias = "crowded_long"
elif latest_sell_ratio > 0.465:
    long_short_bias = "crowded_short"
else:
    long_short_bias = "balanced"

# Data freshness check
collection_time = datetime.fromisoformat(funding_data['collected_at'].replace('Z', '+00:00'))
now = datetime.now(timezone.utc)
age_seconds = (now - collection_time).total_seconds()
stale_after = funding_data['stale_after_seconds']

if age_seconds < stale_after:
    data_freshness = "fresh"
else:
    hours_stale = int(age_seconds / 3600)
    data_freshness = f"stale_{hours_stale}h"

# Prepare perp opportunity description
if funding_regime == "extreme_negative":
    perp_opportunity = f"Extreme negative funding ({latest_funding_pct:.4f}%) presents strong accumulation signal - shorts are being paid relative to longs."
elif funding_regime == "extreme_positive":
    perp_opportunity = f"Extreme positive funding ({latest_funding_pct:.4f}%) presents distribution risk - longs paying significant premium to shorts."
else:
    perp_opportunity = f"Neutral funding environment ({latest_funding_pct:.4f}%) - limited arb opportunity."

# Top signal determination
if funding_regime == "extreme_negative":
    top_signal = "Accumulation opportunity: Extreme negative funding reflects structural underlevering."
elif funding_regime == "extreme_positive":
    top_signal = "Distribution warning: Extreme positive funding signals heavy leverage crowding."
elif oi_trend == "expanding" and latest_buy_ratio > 0.54:
    top_signal = f"Open interest expanding {oi_change_24h:.2f}% with crowded long positioning - elevated leverage tail risk."
elif oi_trend == "contracting":
    top_signal = f"Open interest contracting {oi_change_24h:.2f}% - deleveraging underway."
else:
    top_signal = f"Balanced market structure with {long_short_ratio:.3f} long/short ratio and {oi_change_24h:.2f}% OI change."

# Current timestamp
now_iso = now.isoformat().replace('+00:00', 'Z')

# Create the report
report = {
    "schema_version": "1.0",
    "agent": "derivatives_analyst",
    "produced_at": now_iso,
    "stale_after_seconds": 7200,
    "findings": {
        "funding_regime": funding_regime,
        "funding_rate_latest": round(latest_funding * 100, 6),
        "funding_rate_7d_avg": round(avg_funding_7d * 100, 6),
        "funding_trend": funding_trend,
        "funding_signal": funding_signal,
        "oi_trend": oi_trend,
        "oi_change_24h_pct": round(oi_change_24h, 2),
        "long_short_bias": long_short_bias,
        "long_short_ratio_latest": round(long_short_ratio, 4),
        "derivatives_summary": f"Bitcoin perpetuals showing {funding_regime} funding regime with {oi_trend} open interest ({oi_change_24h:+.2f}% 24h). Long positioning slightly elevated ({latest_buy_ratio*100:.1f}% buy ratio).",
        "perp_opportunity": perp_opportunity,
        "top_derivatives_signal": top_signal,
        "data_freshness": data_freshness
    }
}

print(json.dumps(report, indent=2))

# Save to file
with open('data/analyst_reports/derivatives_analyst.json', 'w') as f:
    json.dump(report, f, indent=2)

print("\n✓ Report written to data/analyst_reports/derivatives_analyst.json")

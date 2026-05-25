#!/usr/bin/env python3
import os
import json
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')

# Load the report
with open('data/analyst_reports/options_analyst.json', 'r') as f:
    report = json.load(f)

spot = report['spot_price']
put_call = report['put_call_analysis']['put_call_oi_ratio']
iv_regime = report['iv_analysis']['regime']
max_pain_weekly = report['max_pain_analysis']['max_pain_weekly']
max_pain_diff_pct = report['max_pain_analysis']['spot_to_max_pain_weekly_diff_pct']
top_signal = report['top_signal']

# Build Discord embed
embed = {
    "title": "📊 BTC Options Daily",
    "color": 3447003,  # blue
    "fields": [
        {
            "name": "Put/Call Ratio",
            "value": f"`{put_call:.4f}` — balanced hedging",
            "inline": True
        },
        {
            "name": "IV Regime",
            "value": f"`{iv_regime.upper()}` — 30D ATM {report['iv_analysis']['iv_30d_atm']*100:.0f}%",
            "inline": True
        },
        {
            "name": "Max Pain (Weekly)",
            "value": f"`${max_pain_weekly:,.0f}` — {max_pain_diff_pct:+.1f}% from spot",
            "inline": True
        },
        {
            "name": "IV Skew",
            "value": f"`{report['iv_skew']['signal']}` — put bias {report['iv_skew']['put_minus_call']:.2f}",
            "inline": True
        },
        {
            "name": "Top Signal",
            "value": top_signal,
            "inline": False
        }
    ],
    "footer": {
        "text": f"Spot: ${spot:,.0f} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    }
}

payload = {
    "embeds": [embed]
}

# Post to Discord
result = subprocess.run(
    ['curl', '-X', 'POST', webhook_url, '-H', 'Content-Type: application/json', '-d', json.dumps(payload)],
    capture_output=True,
    text=True,
    timeout=10
)

if result.returncode == 0:
    print("✓ Notification posted to Discord")
else:
    print(f"ERROR: {result.stderr}")

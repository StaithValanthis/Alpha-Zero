#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

import json
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')
r = requests.get('https://api.alternative.me/fng/?limit=7', timeout=10)
data = r.json().get('data', [])
atomic_write(f'{B}/data/macro/fear_greed_7d.json', envelope('fear_greed', data, 86400))

# Also write flat current file for signal_watcher
if data:
    current = {
        "schema_version": "1.0",
        "source": "fear_greed_7d.json",
        "produced_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "value": int(data[0]["value"]),
        "value_classification": data[0].get("value_classification", "?")
    }
    tmp = f'{B}/data/macro/fear_greed_current.json.tmp'
    with open(tmp, 'w') as f: json.dump(current, f, indent=2)
    os.rename(tmp, f'{B}/data/macro/fear_greed_current.json')

print("fear_greed: OK")

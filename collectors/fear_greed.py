#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

import json
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')
output_file = f'{B}/data/macro/fear_greed_7d.json'

try:
    r = requests.get('https://api.alternative.me/fng/?limit=7', timeout=10)
    data = r.json().get('data', [])
    atomic_write(output_file, envelope('fear_greed', data, 86400))
    
    # Also write flat current file for signal_watcher
    if data:
        try:
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
        except Exception as e:
            print(f"fear_greed: warning - failed to write current file: {e}")
    
    print("fear_greed: OK")

except Exception as e:
    if os.path.exists(output_file):
        print(f"fear_greed: warning - fetch failed, keeping existing file: {e}")
    else:
        stub_data = [{
            "value": None,
            "value_classification": "unknown",
            "source": "unavailable",
            "error": str(e)
        }]
        atomic_write(output_file, envelope('fear_greed', stub_data, 86400))
        print(f"fear_greed: warning - wrote stub due to error: {e}")

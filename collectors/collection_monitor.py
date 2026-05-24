#!/usr/bin/env python3
import os, json, time
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')
CHECKS = {
    'btc_candles': (f'{B}/data/market/btc_candles_1h.json', 360),
    'derivatives': (f'{B}/data/market/funding_history.json', 3600),
    'fear_greed':  (f'{B}/data/macro/fear_greed_7d.json', 90000),
    'onchain':     (f'{B}/data/onchain/mempool.json', 4000),
    'ta_engine':   (f'{B}/data/indicators/btc_4h.json', 400),
}
while True:
    now = time.time()
    status = {}
    for name, (path, stale) in CHECKS.items():
        try:
            age = int(now - os.path.getmtime(path))
            h = 'green' if age < stale else 'yellow' if age < stale*2 else 'red'
            status[name] = {'health': h, 'age_seconds': age}
        except:
            status[name] = {'health': 'red', 'age_seconds': -1}
    tmp = f'{B}/data/meta/collection_status.json.tmp'
    with open(tmp,'w') as f:
        json.dump({'checked_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'collectors': status}, f)
    os.rename(tmp, f'{B}/data/meta/collection_status.json')
    time.sleep(300)

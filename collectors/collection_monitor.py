#!/usr/bin/env python3
import os, json, time
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')
CHECKS = {
    'btc_candles':    (f'{B}/data/market/btc_candles_1h.json',        360),
    'derivatives':    (f'{B}/data/market/funding_history.json',       3600),
    'fear_greed':     (f'{B}/data/macro/fear_greed_7d.json',         90000),
    'onchain':        (f'{B}/data/onchain/mempool.json',             90000),
    'ta_engine':      (f'{B}/data/indicators/btc_4h.json',            400),
    # New tier-1 collectors
    'news':           (f'{B}/data/news/articles.json',               1800),
    'news_classified':(f'{B}/data/news/classified.json',             5000),
    'options':        (f'{B}/data/options/btc_options.json',         4000),
    'etf_flows':      (f'{B}/data/macro/etf/flows.json',            50000),
    'whales':         (f'{B}/data/whales/large_transactions.json',   3600),
    'netflow':        (f'{B}/data/onchain/netflow.json',             8000),
    'alt_watchlist':  (f'{B}/data/alts/watchlist_prices.json',      90000),
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

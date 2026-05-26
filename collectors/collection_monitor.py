#!/usr/bin/env python3
"""Collection monitor — file-age AND content-freshness health for collectors.

Original behavior only checked file mtime, so a collector that keeps rewriting
its file with identical data (e.g. a dead/paywalled source still serving a
cached feed — see the cryptocurrency.cv 402 news incident) stayed 'green'
forever. This version also fingerprints the meaningful content and flags a
collector whose data hasn't actually changed in a long time.

Writes data/meta/collection_status.json (enriched, backward-compatible:
'health' is still present; adds 'file_health', 'content_health',
'content_unchanged_seconds'). Content-change state persists in
data/meta/collection_content_state.json.
"""
import os, json, time, hashlib
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')
META = f'{B}/data/meta'
STATUS = f'{META}/collection_status.json'
CONTENT_STATE = f'{META}/collection_content_state.json'

# name: (path, file_stale_seconds)
CHECKS = {
    'btc_candles':     (f'{B}/data/market/btc_candles_1h.json',     360),
    'derivatives':     (f'{B}/data/market/funding_history.json',    3600),
    'fear_greed':      (f'{B}/data/macro/fear_greed_7d.json',       90000),
    'onchain':         (f'{B}/data/onchain/mempool.json',           90000),
    'ta_engine':       (f'{B}/data/indicators/btc_4h.json',         400),
    'news':            (f'{B}/data/news/articles.json',             1800),
    'news_classified': (f'{B}/data/news/classified.json',           5000),
    'options':         (f'{B}/data/options/btc_options.json',       4000),
    'etf_flows':       (f'{B}/data/macro/etf/flows.json',           50000),
    'whales':          (f'{B}/data/whales/large_transactions.json', 3600),
    'netflow':         (f'{B}/data/onchain/netflow.json',           8000),
    'alt_watchlist':   (f'{B}/data/alts/watchlist_prices.json',     90000),
}

# Content counts as stale if the meaningful data hasn't changed in this long,
# even while the file keeps being rewritten. 12x the file threshold (floored at
# 1h) — generous enough to avoid false positives on genuinely quiet periods,
# tight enough that a multi-day dead source (the news case) trips it.
def content_stale_threshold(file_stale):
    return max(file_stale * 12, 3600)

# Per-write churn keys that aren't "real" content — excluded from the
# fingerprint so identical payloads hash the same across writes.
_VOLATILE_KEYS = {'collected_at', 'checked_at', 'fetched_at', 'timestamp',
                  'last_updated', 'produced_at', 'generated_at', 'updated_at', 'as_of'}


def _content_fingerprint(path):
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        obj = json.loads(raw)
    except Exception:
        return hashlib.sha256(raw).hexdigest()
    if isinstance(obj, dict) and 'data' in obj:
        obj = obj['data']                       # inner payload of wrapped files
    elif isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k not in _VOLATILE_KEYS}
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


while True:
    now = time.time()
    nowiso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    content_state = _load_json(CONTENT_STATE, {})
    if not isinstance(content_state, dict):
        content_state = {}
    status = {}
    for name, (path, stale) in CHECKS.items():
        try:
            age = int(now - os.path.getmtime(path))
            file_h = 'green' if age < stale else 'yellow' if age < stale * 2 else 'red'
        except Exception:
            status[name] = {'health': 'red', 'file_health': 'red', 'content_health': 'red',
                            'age_seconds': -1, 'content_unchanged_seconds': -1}
            content_state.pop(name, None)
            continue
        try:
            fp = _content_fingerprint(path)
            prev = content_state.get(name)
            if not isinstance(prev, dict) or prev.get('hash') != fp:
                content_state[name] = {'hash': fp, 'since': now}
            unchanged = int(now - content_state[name]['since'])
            cthr = content_stale_threshold(stale)
            content_h = 'green' if unchanged < cthr else 'yellow' if unchanged < cthr * 2 else 'red'
        except Exception:
            unchanged = -1
            content_h = 'green'   # never penalize on a fingerprint error
        # Quick data_count check — catches a source writing 0-record envelopes immediately
        # (doesn't wait for content_unchanged to accumulate over hours)
        data_count = -1
        try:
            with open(path) as fp:
                d = json.load(fp)
            if isinstance(d, dict) and 'data' in d and isinstance(d['data'], list):
                data_count = len(d['data'])
                if data_count == 0:
                    content_h = 'red'
        except Exception:
            pass
        overall = 'red' if 'red' in (file_h, content_h) else 'yellow' if 'yellow' in (file_h, content_h) else 'green'
        status[name] = {'health': overall, 'file_health': file_h, 'content_health': content_h,
                        'age_seconds': age, 'content_unchanged_seconds': unchanged,
                        'data_count': data_count}
    os.makedirs(META, exist_ok=True)
    tmp = f'{STATUS}.tmp'
    with open(tmp, 'w') as f:
        json.dump({'checked_at': nowiso, 'collectors': status}, f)
    os.rename(tmp, STATUS)
    ctmp = f'{CONTENT_STATE}.tmp'
    with open(ctmp, 'w') as f:
        json.dump(content_state, f)
    os.rename(ctmp, CONTENT_STATE)
    time.sleep(300)

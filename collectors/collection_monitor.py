#!/usr/bin/env python3
"""Collection monitor — file-age, content-freshness, AND semantic record age.

Three layers of health checking:
  1. file_health   — mtime vs stale threshold
  2. content_health — fingerprint (did meaningful data change?) + data_count=0 check
  3. newest_record_age_seconds — age of the most-recent dated record inside the file
     (catches "degraded-but-writing": file fresh, content changing, but all records old)

Writes data/meta/collection_status.json (backward-compatible: 'health' always present).
Content-change state persists in data/meta/collection_content_state.json.
"""
import os, json, time, hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

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

# Semantic date field mapping: collector -> dot-notation path to the date field
# in each record of data[]. Used to compute newest_record_age_seconds.
# Only collectors where record recency matters are listed.
SEMANTIC_DATE_FIELDS = {
    'news':            'published_at',   # RFC 2822 from CoinDesk / ISO from other sources
    'news_classified': 'published_at',
    'netflow':         'date',           # 'YYYY-MM-DD' daily
    'etf_flows':       'date',           # 'YYYY-MM-DD' daily
    'fear_greed':      'timestamp',      # unix timestamp string
    'whales':          'timestamp',
}

# Alert threshold: if newest_record_age_seconds exceeds this, content_health -> yellow/red
# Values tuned to each collector's expected data freshness (not file freshness)
SEMANTIC_STALE_WARN = {
    'news':            6 * 3600,         # news older than 6h is stale
    'news_classified': 6 * 3600,
    'netflow':         36 * 3600,        # daily data, some lag normal
    'etf_flows':       48 * 3600,        # daily ETF flows, T+1 reporting lag
    'fear_greed':      30 * 3600,        # updates daily
    'whales':          4 * 3600,
}


def _parse_record_dt(value):
    """Parse a date string from a data record. Tries RFC 2822, ISO 8601, and unix ts."""
    if value is None:
        return None
    # Unix timestamp (integer or numeric string)
    try:
        ts = float(value)
        # Binance-style ms timestamps
        if ts > 1e12:
            ts /= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    # RFC 2822
    try:
        return parsedate_to_datetime(str(value))
    except Exception:
        pass
    # ISO 8601 / date-only
    s = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _newest_record_age(path, date_field):
    """Return seconds since the newest record's date, or -1 on any error."""
    try:
        with open(path) as f:
            d = json.load(f)
        records = d.get('data', []) if isinstance(d, dict) else d
        if not isinstance(records, list) or not records:
            return -1
        best_dt = None
        for rec in records:
            val = rec.get(date_field) if isinstance(rec, dict) else None
            dt = _parse_record_dt(val)
            if dt and (best_dt is None or dt > best_dt):
                best_dt = dt
        if best_dt is None:
            return -1
        return int((datetime.now(timezone.utc) - best_dt).total_seconds())
    except Exception:
        return -1


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
        # Semantic record-age check: is the newest dated record actually recent?
        # This catches degraded-but-writing sources (file fresh, content changing via
        # article expiry, but no genuinely new records — e.g. the news 402 incident).
        newest_record_age = -1
        if name in SEMANTIC_DATE_FIELDS:
            newest_record_age = _newest_record_age(path, SEMANTIC_DATE_FIELDS[name])
            if newest_record_age > 0 and name in SEMANTIC_STALE_WARN:
                warn_thr = SEMANTIC_STALE_WARN[name]
                if newest_record_age > warn_thr * 2:
                    content_h = 'red'
                elif newest_record_age > warn_thr and content_h == 'green':
                    content_h = 'yellow'
        overall = 'red' if 'red' in (file_h, content_h) else 'yellow' if 'yellow' in (file_h, content_h) else 'green'
        status[name] = {'health': overall, 'file_health': file_h, 'content_health': content_h,
                        'age_seconds': age, 'content_unchanged_seconds': unchanged,
                        'data_count': data_count, 'newest_record_age_seconds': newest_record_age}
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

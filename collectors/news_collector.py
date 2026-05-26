#!/usr/bin/env python3
"""News collector — cryptocurrency.cv API with CoinDesk RSS fallback. No LLM."""
import sys, os, json, time, re
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

BASE = os.path.expanduser('~/btc-agents')
ARTICLES_PATH = f'{BASE}/data/news/articles.json'
FLAGGED_PATH  = f'{BASE}/data/news/flagged.json'

TIER1_KEYWORDS = [
    "hack", "hacked", "exploit", "drained", "insolvent", "insolvency",
    "bankrupt", "ban", "banned", "prohibit", "depeg", "depegged",
    "sec charges", "doj", "arrest", "seized", "shutdown", "emergency",
    "circuit breaker",
]

HEADERS = {'User-Agent': 'btc-agents/1.0 (data collector)'}


def fetch_cryptocv():
    url = 'https://cryptocurrency.cv/api/v1/news?category=bitcoin&limit=50'
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    raw = json.loads(resp.read())
    articles = []
    items = raw if isinstance(raw, list) else raw.get('data', raw.get('articles', raw.get('news', [])))
    for a in items:
        articles.append({
            'id':           str(a.get('id', '')),
            'title':        a.get('title', ''),
            'url':          a.get('url', a.get('link', '')),
            'source':       a.get('source', a.get('domain', 'cryptocurrency.cv')),
            'published_at': a.get('published_at', a.get('date', a.get('created_at', ''))),
            'summary':      a.get('summary', a.get('description', '')),
        })
    return articles


def fetch_coindesk_rss():
    url = 'https://www.coindesk.com/arc/outboundfeeds/rss/'
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    xml_data = resp.read()
    root = ET.fromstring(xml_data)
    ns = {'content': 'http://purl.org/rss/1.0/modules/content/'}
    articles = []
    for item in root.findall('.//item'):
        title = item.findtext('title', '')
        link  = item.findtext('link', '')
        desc  = item.findtext('description', '')
        pub   = item.findtext('pubDate', '')
        if 'bitcoin' in (title + desc).lower():
            articles.append({
                'id':           link,
                'title':        title,
                'url':          link,
                'source':       'CoinDesk',
                'published_at': pub,
                'summary':      desc[:300] if desc else '',
            })
    return articles


def load_existing():
    if os.path.exists(ARTICLES_PATH):
        try:
            d = json.load(open(ARTICLES_PATH))
            return d.get('data', [])
        except Exception:
            pass
    return []


def parse_dt(s):
    if not s:
        return None
    # Try email.utils first — handles RFC 2822 format correctly without truncation.
    # The old [:30] truncation silently corrupted CoinDesk timestamps (31 chars)
    # causing all CoinDesk dates to return None and never expire from the 48h window.
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s)
    except Exception:
        pass
    # ISO 8601 and other formats — use the full string, not a truncated slice
    for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S'):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def is_flagged(article):
    text = (article.get('title', '') + ' ' + article.get('summary', '')).lower()
    for kw in TIER1_KEYWORDS:
        if kw in text:
            return kw
    return None


def main():
    source_used = 'cryptocurrency.cv'
    try:
        fetched = fetch_cryptocv()
        print(f"cryptocurrency.cv: {len(fetched)} articles")
    except Exception as e:
        print(f"cryptocurrency.cv failed ({e}), trying CoinDesk RSS...")
        source_used = 'coindesk-rss'
        try:
            fetched = fetch_coindesk_rss()
            print(f"CoinDesk RSS: {len(fetched)} articles")
        except Exception as e2:
            print(f"CoinDesk RSS also failed ({e2}). Writing empty.")
            fetched = []

    existing = load_existing()
    existing_urls = {a['url'] for a in existing}

    now = datetime.now(timezone.utc)
    cutoff_48h = now - timedelta(hours=48)
    cutoff_24h = now - timedelta(hours=24)

    new_count = 0
    for a in fetched:
        if a['url'] and a['url'] not in existing_urls:
            existing.append(a)
            existing_urls.add(a['url'])
            new_count += 1

    # Drop articles older than 48h
    kept = []
    for a in existing:
        dt = parse_dt(a.get('published_at', ''))
        if dt is None or dt >= cutoff_48h:
            kept.append(a)
    existing = kept

    atomic_write(ARTICLES_PATH, envelope('news_collector', existing, stale_after=3600))

    # Keyword flagging over last 24h
    flagged = []
    for a in existing:
        dt = parse_dt(a.get('published_at', ''))
        in_window = dt is None or dt >= cutoff_24h
        if in_window:
            kw = is_flagged(a)
            if kw:
                flagged.append({**a, 'matched_keyword': kw, 'flagged_at': now.strftime('%Y-%m-%dT%H:%M:%SZ')})

    existing_flagged = []
    if os.path.exists(FLAGGED_PATH):
        try:
            existing_flagged = json.load(open(FLAGGED_PATH)).get('data', [])
        except Exception:
            pass
    flagged_urls = {f['url'] for f in existing_flagged}
    for f in flagged:
        if f['url'] not in flagged_urls:
            existing_flagged.append(f)
    # Keep 48h window on flagged too
    existing_flagged = [f for f in existing_flagged
                        if parse_dt(f.get('published_at', '')) is None
                        or parse_dt(f.get('published_at', '')) >= cutoff_48h]
    atomic_write(FLAGGED_PATH, envelope('news_collector', existing_flagged, stale_after=3600))

    print(f"news_collector: OK | source={source_used} | total={len(existing)} | new={new_count} | flagged={len(flagged)}")


if __name__ == '__main__':
    main()

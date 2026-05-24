#!/usr/bin/env python3
"""News classifier — Gemini Flash. Reads articles.json, classifies sentiment/tier, writes classified.json."""
import sys, os, json, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

BASE = os.path.expanduser('~/btc-agents')
ARTICLES_PATH   = f'{BASE}/data/news/articles.json'
CLASSIFIED_PATH = f'{BASE}/data/news/classified.json'
HEADERS = {'Content-Type': 'application/json'}

TIER1_KEYWORDS = [
    "hack", "hacked", "exploit", "drained", "insolvent", "insolvency",
    "bankrupt", "ban", "banned", "prohibit", "depeg", "depegged",
    "sec charges", "doj", "arrest", "seized", "shutdown", "emergency",
]

GEMINI_URL = ('https://generativelanguage.googleapis.com/v1beta/models/'
              'gemini-2.5-flash:generateContent?key={key}')

CLASSIFY_PROMPT = """Classify the following Bitcoin news articles. For each article return a JSON object with:
- "id": the article id
- "sentiment": one of "bullish", "bearish", "neutral"
- "tier": 1 (high-impact: ETF, regulation, exchange hack, macro), 2 (moderate: price analysis, adoption), or 3 (low: minor news)
- "summary": one sentence max, capturing the key fact

Return ONLY a JSON array of these objects. No extra text.

Articles:
{articles}"""


def load_articles():
    if not os.path.exists(ARTICLES_PATH):
        return []
    try:
        d = json.load(open(ARTICLES_PATH))
        return d.get('data', [])
    except Exception:
        return []


def load_existing_classified():
    if not os.path.exists(CLASSIFIED_PATH):
        return []
    try:
        d = json.load(open(CLASSIFIED_PATH))
        return d.get('data', [])
    except Exception:
        return []


def classify_batch(articles, api_key):
    """Send up to 20 articles to Gemini. Uses numeric index to avoid URL-in-JSON issues."""
    article_text = '\n'.join(
        f'[{i+1}] {a.get("title","")} — {a.get("summary","")[:150]}'
        for i, a in enumerate(articles)
    )
    prompt = CLASSIFY_PROMPT.format(articles=article_text)

    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 4096},
    }
    url = GEMINI_URL.format(key=api_key)
    req = Request(url, data=json.dumps(payload).encode(), headers=HEADERS, method='POST')
    resp = urlopen(req, timeout=30)
    raw = json.loads(resp.read())

    text = raw['candidates'][0]['content']['parts'][0]['text'].strip()
    if text.startswith('```'):
        lines = text.splitlines()
        text = '\n'.join(l for l in lines if not l.startswith('```'))
    text = text.replace("\\'", "'")

    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        import re as _re
        m = _re.search(r'\[.*\]', text, _re.DOTALL)
        results = json.loads(m.group(0)) if m else []

    # Map by numeric position (Gemini returns id=1,2,3...)
    indexed = {str(r.get('id', '')): r for r in results}
    out = []
    for i, art in enumerate(articles):
        classification = indexed.get(str(i + 1), {})
        out.append({
            'article_id':  art['id'],
            'sentiment':   classification.get('sentiment', 'neutral'),
            'tier':        classification.get('tier', 3),
            'ai_summary':  classification.get('summary', ''),
        })
    return out


def post_discord_tier1(article, env):
    webhook = env.get('DISCORD_WEBHOOK_URL', '')
    if not webhook:
        return
    sentiment_color = {'bullish': 3066993, 'bearish': 15158332, 'neutral': 10197915}
    color = sentiment_color.get(article.get('sentiment', 'neutral'), 10197915)
    payload = {'embeds': [{
        'title': f"🚨 Tier-1 News: {article.get('title','')[:100]}",
        'color': color,
        'fields': [
            {'name': 'Sentiment', 'value': article.get('sentiment', '?'), 'inline': True},
            {'name': 'Source',    'value': article.get('source', '?'),    'inline': True},
            {'name': 'Summary',   'value': article.get('summary', '')[:200], 'inline': False},
        ],
        'url': article.get('url', ''),
    }]}
    try:
        req = Request(webhook, data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
        urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Discord alert failed: {e}")


def keyword_tier1(article):
    text = (article.get('title', '') + ' ' + article.get('summary', '')).lower()
    return any(kw in text for kw in TIER1_KEYWORDS)


def main():
    env = load_env()
    api_key = env.get('GEMINI_API_KEY', '')
    if not api_key:
        print("news_classifier: WARNING — no GEMINI_API_KEY")
        return

    articles = load_articles()
    if not articles:
        print("news_classifier: no articles to classify")
        return

    existing = load_existing_classified()
    existing_ids = {a['id'] for a in existing}

    # Only classify articles from the last 24h that haven't been classified
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    def parse_dt(s):
        if not s:
            return None
        for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z',
                    '%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z',
                    '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(s[:30].strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

    to_classify = [
        a for a in articles
        if a.get('id') and a['id'] not in existing_ids
        and (parse_dt(a.get('published_at')) or now) >= cutoff
    ]

    print(f"Articles to classify: {len(to_classify)} (of {len(articles)} total)")

    newly_classified = []
    if to_classify and api_key:
        # Process in batches of 20
        for i in range(0, len(to_classify), 20):
            batch = to_classify[i:i+20]
            try:
                results = classify_batch(batch, api_key)
                # results is a list aligned with batch order
                result_map = {r['article_id']: r for r in results}
                for art in batch:
                    cl = result_map.get(art['id'], {})
                    classified = {
                        **art,
                        'sentiment':    cl.get('sentiment', 'neutral'),
                        'tier':         cl.get('tier', 3),
                        'ai_summary':   cl.get('ai_summary', ''),
                        'classified_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    }
                    newly_classified.append(classified)
                print(f"  Classified batch {i//20+1}: {len(batch)} articles")
                if i + 20 < len(to_classify):
                    time.sleep(1)  # rate limit courtesy
            except Exception as e:
                print(f"  Gemini batch failed: {e}")
                # Fall back to keyword-based tier assignment
                for art in batch:
                    classified = {
                        **art,
                        'sentiment':    'neutral',
                        'tier':         1 if keyword_tier1(art) else 3,
                        'ai_summary':   '',
                        'classified_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'classification_error': str(e),
                    }
                    newly_classified.append(classified)

    # Merge into existing
    all_classified = existing + newly_classified
    # Drop articles older than 48h
    cutoff_48h = now - timedelta(hours=48)
    all_classified = [
        a for a in all_classified
        if (parse_dt(a.get('published_at')) or now) >= cutoff_48h
    ]

    atomic_write(CLASSIFIED_PATH, envelope('news_classifier', all_classified, stale_after=4000))

    # Post Tier-1 alerts to Discord (new only)
    tier1_new = [a for a in newly_classified if a.get('tier') == 1]
    for art in tier1_new:
        post_discord_tier1(art, env)

    tier1_count   = sum(1 for a in all_classified if a.get('tier') == 1)
    bullish_count = sum(1 for a in all_classified if a.get('sentiment') == 'bullish')
    bearish_count = sum(1 for a in all_classified if a.get('sentiment') == 'bearish')

    print(f"news_classifier: OK | total={len(all_classified)} | new={len(newly_classified)} "
          f"| tier1={tier1_count} | bullish={bullish_count} bearish={bearish_count}")


if __name__ == '__main__':
    main()

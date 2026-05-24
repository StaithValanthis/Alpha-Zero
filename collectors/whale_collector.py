#!/usr/bin/env python3
"""Whale transaction collector — Blockchair primary (free, no key), mempool.space fallback."""
import sys, os, json, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

BASE = os.path.expanduser('~/btc-agents')
OUT  = f'{BASE}/data/whales/large_transactions.json'
HEADERS = {'User-Agent': 'btc-agents/1.0'}
MIN_BTC = 500
MIN_SATS = MIN_BTC * 100_000_000


def fetch_blockchair(retries=2):
    url = (f'https://api.blockchair.com/bitcoin/transactions'
           f'?q=output_total({MIN_SATS}..)&limit=10&s=time(desc)')
    for attempt in range(retries):
        try:
            r = urlopen(Request(url, headers=HEADERS), timeout=20)
            raw = json.loads(r.read())
            if 'data' not in raw:
                raise ValueError(f"No data key: {list(raw.keys())}")
            txns = []
            for tx in raw['data']:
                sats = tx.get('output_total', 0)
                txns.append({
                    'hash':         tx.get('hash', ''),
                    'time':         tx.get('time', ''),
                    'output_btc':   round(sats / 1e8, 2),
                    'output_usd':   tx.get('output_total_usd', 0),
                    'input_count':  tx.get('input_count', 0),
                    'output_count': tx.get('output_count', 0),
                    'is_coinbase':  tx.get('is_coinbase', False),
                })
            return txns
        except HTTPError as e:
            if e.code == 430 and attempt < retries - 1:
                time.sleep(8)
                continue
            raise


def fetch_mempool_fallback():
    """Scan the last 2 confirmed blocks for large-output transactions."""
    # Get recent block hashes
    r = urlopen(Request('https://mempool.space/api/blocks', headers=HEADERS), timeout=15)
    blocks = json.loads(r.read())[:2]

    txns = []
    seen = set()
    for block in blocks:
        bh = block.get('id', '')
        if not bh:
            continue
        # Get first page of transactions (25 txns ordered by fee)
        time.sleep(0.5)
        try:
            r = urlopen(Request(f'https://mempool.space/api/block/{bh}/txs/0', headers=HEADERS), timeout=15)
            block_txns = json.loads(r.read())
        except Exception:
            continue

        for tx in block_txns:
            txid = tx.get('txid', '')
            if txid in seen:
                continue
            seen.add(txid)

            # Sum all vouts
            total_sats = sum(v.get('value', 0) for v in tx.get('vout', []))
            if total_sats >= MIN_SATS:
                txns.append({
                    'hash':         txid,
                    'time':         datetime.fromtimestamp(tx.get('status', {}).get('block_time', 0), tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                    'output_btc':   round(total_sats / 1e8, 2),
                    'output_usd':   None,
                    'input_count':  len(tx.get('vin', [])),
                    'output_count': len(tx.get('vout', [])),
                    'is_coinbase':  tx.get('vin', [{}])[0].get('is_coinbase', False),
                })

    return txns


def post_discord_alert(txns, env):
    webhook = env.get('DISCORD_WEBHOOK_URL', '')
    if not webhook:
        return
    very_large = [t for t in txns if t.get('output_btc', 0) >= 1000]
    if not very_large:
        return
    for tx in very_large[:2]:
        btc = tx['output_btc']
        usd = tx.get('output_usd')
        payload = {'embeds': [{'title': f'🐋 Whale Alert: {btc:,.0f} BTC moved',
            'color': 3447003,
            'fields': [
                {'name': 'BTC', 'value': f'{btc:,.2f} BTC', 'inline': True},
                {'name': 'USD', 'value': f'${usd:,.0f}' if usd else 'n/a', 'inline': True},
                {'name': 'Hash', 'value': tx['hash'][:20] + '...', 'inline': False},
                {'name': 'Time (UTC)', 'value': tx['time'], 'inline': True},
            ]}]}
        try:
            req = Request(webhook, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
            urlopen(req, timeout=10)
        except Exception as e:
            print(f"  Discord alert failed: {e}")


def main():
    env = load_env()
    result = None
    source = None

    try:
        txns = fetch_blockchair()
        source = 'blockchair'
        print(f"Blockchair: {len(txns)} transactions ≥{MIN_BTC} BTC")
    except Exception as e:
        print(f"Blockchair failed ({e}), trying mempool.space...")
        try:
            txns = fetch_mempool_fallback()
            source = 'mempool.space'
            print(f"mempool.space: {len(txns)} large transactions in last 2 blocks")
        except Exception as e2:
            txns = None
            print(f"mempool.space also failed: {e2}")

    if txns is not None:
        post_discord_alert(txns, env)
        result = {
            'source':        source,
            'min_output_btc': MIN_BTC,
            'transactions':   txns,
            'count':          len(txns),
            'largest_btc':    max((t['output_btc'] for t in txns), default=0),
        }
        if txns:
            print(f"  Largest: {result['largest_btc']:,.0f} BTC")
    else:
        result = {
            'source':       'unavailable',
            'note':         'All sources rate-limited or unavailable. Will retry next run.',
            'transactions': [],
            'count':        0,
        }

    atomic_write(OUT, envelope('whale_collector', result, stale_after=1800))
    print(f"whale_collector: {'OK' if txns is not None else 'WARNING'} | source={result['source']} | count={result.get('count', 0)}")


if __name__ == '__main__':
    main()

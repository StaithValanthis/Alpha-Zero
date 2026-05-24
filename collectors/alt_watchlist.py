#!/usr/bin/env python3
import sys, os, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

B = os.path.expanduser('~/btc-agents'); env = load_env()
URL = env.get('BYBIT_BASE_URL', 'https://api.bybit.com')
watchlist = json.load(open(f'{B}/state/watchlist.json')).get('alts', [])
prices = {}
for sym in watchlist:
    try:
        r = requests.get(f'{URL}/v5/market/tickers', params={'category':'spot','symbol':sym}, timeout=5)
        d = r.json()
        if d.get('retCode') == 0:
            t = d['result']['list'][0] if d['result']['list'] else {}
            prices[sym] = {'lastPrice': t.get('lastPrice'), 'price24hPcnt': t.get('price24hPcnt'), 'volume24h': t.get('volume24h')}
    except Exception as e: prices[sym] = {'error': str(e)}
atomic_write(f'{B}/data/alts/watchlist_prices.json', envelope('alt_watchlist', prices, 900))
print(f"alt_watchlist: OK ({len(prices)} symbols)")

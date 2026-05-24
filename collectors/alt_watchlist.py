#!/usr/bin/env python3
import sys, os, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

B = os.path.expanduser('~/btc-agents'); env = load_env()
URL = env.get('BYBIT_BASE_URL', 'https://api.bybit.com')

# Primary: state/symbol_watchlist.json (static config)
# Fallback: universe_details[*].symbol from state/watchlist.json (scanner output)
def load_symbols():
    try:
        d = json.load(open(f'{B}/state/symbol_watchlist.json'))
        syms = d.get('symbols', [])
        if syms:
            return syms
    except Exception:
        pass
    try:
        d = json.load(open(f'{B}/state/watchlist.json'))
        details = d.get('universe_details', [])
        syms = [item['symbol'] for item in details if item.get('symbol')]
        if syms:
            return syms
    except Exception:
        pass
    return []

watchlist = load_symbols()
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

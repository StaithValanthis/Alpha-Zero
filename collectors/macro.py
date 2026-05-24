#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

B = os.path.expanduser('~/btc-agents')
try:
    r = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true', timeout=10)
    atomic_write(f'{B}/data/macro/btc_market.json', envelope('macro', r.json(), 1800))
except Exception as e: print(f"macro: {e}")
print("macro: OK")

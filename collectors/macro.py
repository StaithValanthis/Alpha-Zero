#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

B = os.path.expanduser('~/btc-agents')
output_file = f'{B}/data/macro/btc_market.json'

try:
    r = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true', timeout=10)
    atomic_write(output_file, envelope('macro', r.json(), 1800))
    print("macro: OK")
except Exception as e:
    if os.path.exists(output_file):
        print(f"macro: warning - fetch failed, keeping existing file: {e}")
    else:
        print(f"macro: warning - fetch failed and no existing file: {e}")

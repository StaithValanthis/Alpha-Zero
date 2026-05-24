#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

B = os.path.expanduser('~/btc-agents')
try:
    r = requests.get('https://mempool.space/api/v1/fees/recommended', timeout=10)
    atomic_write(f'{B}/data/onchain/mempool.json', envelope('onchain', r.json(), 3600))
except Exception as e: print(f"mempool: {e}")
try:
    r = requests.get('https://api.blockchair.com/bitcoin/stats', timeout=10)
    atomic_write(f'{B}/data/onchain/blockchair.json', envelope('onchain', r.json().get('data',{}), 3600))
except Exception as e: print(f"blockchair: {e}")
print("onchain: OK")

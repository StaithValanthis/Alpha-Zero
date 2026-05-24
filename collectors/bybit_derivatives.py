#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

B = os.path.expanduser('~/btc-agents'); env = load_env()
URL = env.get('BYBIT_BASE_URL', 'https://api.bybit.com')

def get(path, params):
    return requests.get(f'{URL}{path}', params=params, timeout=10).json()

d = get('/v5/market/funding/history', {'category':'linear','symbol':'BTCUSDT','limit':50})
atomic_write(f'{B}/data/market/funding_history.json', envelope('derivatives', d.get('result',{}).get('list',[]), 3600))
d = get('/v5/market/open-interest', {'category':'linear','symbol':'BTCUSDT','intervalTime':'1h','limit':24})
atomic_write(f'{B}/data/market/open_interest.json', envelope('derivatives', d.get('result',{}).get('list',[]), 3600))
d = get('/v5/market/account-ratio', {'category':'linear','symbol':'BTCUSDT','period':'1h','limit':24})
atomic_write(f'{B}/data/market/long_short_ratio.json', envelope('derivatives', d.get('result',{}).get('list',[]), 3600))
print("bybit_derivatives: OK")

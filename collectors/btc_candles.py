#!/usr/bin/env python3
import sys, os, requests, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

B = os.path.expanduser('~/btc-agents'); env = load_env()
URL = env.get('BYBIT_BASE_URL', 'https://api.bybit.com')

# Map Bybit interval strings to Binance interval strings
INTERVAL_MAP = {
    '1': '1m',
    '60': '1h',
    '240': '4h',
    'D': '1d'
}

def fetch(interval, limit, out):
    # Try Bybit first
    try:
        r = requests.get(f'{URL}/v5/market/kline',
            params={'category':'spot','symbol':'BTCUSDT','interval':interval,'limit':limit}, timeout=10)
        d = r.json()
        if d.get('retCode') != 0: raise Exception(d)
        candles = sorted([{'ts':int(c[0]),'open':float(c[1]),'high':float(c[2]),
            'low':float(c[3]),'close':float(c[4]),'volume':float(c[5])}
            for c in d['result']['list']], key=lambda x: x['ts'])
        print(f'btc_candles [{interval}]: source=bybit')
        atomic_write(out, envelope('btc_candles', candles, 360))
    except Exception as e:
        # Fallback to Binance
        try:
            binance_interval = INTERVAL_MAP[interval]
            r = requests.get('https://api.binance.com/api/v3/klines',
                params={'symbol': 'BTCUSDT', 'interval': binance_interval, 'limit': limit}, timeout=10)
            d = r.json()
            if not isinstance(d, list): raise Exception(f'Unexpected Binance response: {d}')
            candles = sorted([{'ts':int(c[0]),'open':float(c[1]),'high':float(c[2]),
                'low':float(c[3]),'close':float(c[4]),'volume':float(c[9])}
                for c in d], key=lambda x: x['ts'])
            print(f'btc_candles [{interval}]: source=binance')
            atomic_write(out, envelope('btc_candles', candles, 360))
        except Exception as binance_error:
            print(f'btc_candles [{interval}]: Bybit failed: {e}, Binance failed: {binance_error}', file=sys.stderr)
            raise

fetch('1',   500, f'{B}/data/market/btc_candles_1m.json')
fetch('60',  200, f'{B}/data/market/btc_candles_1h.json')
fetch('240', 90,  f'{B}/data/market/btc_candles_4h.json')
fetch('D',   90,  f'{B}/data/market/btc_candles_1d.json')
subprocess.Popen([sys.executable, f'{B}/tools/ta_engine.py'])
print('btc_candles: OK')

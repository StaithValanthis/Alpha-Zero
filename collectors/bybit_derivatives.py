#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

B = os.path.expanduser('~/btc-agents'); env = load_env()
BYBIT_URL = env.get('BYBIT_BASE_URL', 'https://api.bybit.com')
BINANCE_URL = 'https://fapi.binance.com'

def get_funding_history():
    """Fetch funding history from Bybit, fallback to Binance."""
    # Try Bybit first
    try:
        resp = requests.get(f'{BYBIT_URL}/v5/market/funding/history', 
                           params={'category':'linear','symbol':'BTCUSDT','limit':50}, 
                           timeout=10).json()
        data = resp.get('result',{}).get('list',[])
        for item in data:
            item['source'] = 'bybit'
        return data
    except Exception as e:
        print(f'Bybit funding_history failed: {e}, trying Binance...', file=sys.stderr)
    
    # Fallback to Binance
    try:
        resp = requests.get(f'{BINANCE_URL}/fapi/v1/fundingRate',
                           params={'symbol':'BTCUSDT','limit':50},
                           timeout=10).json()
        # Normalize Binance response to match Bybit format
        # Binance returns: {symbol, fundingTime, fundingRate, markPrice}
        # Convert to: {ts, funding_rate, symbol, source}
        data = []
        for item in resp:
            data.append({
                'ts': str(item['fundingTime']),
                'funding_rate': item['fundingRate'],
                'symbol': item['symbol'],
                'source': 'binance'
            })
        return data
    except Exception as e:
        print(f'Binance funding_history failed: {e}', file=sys.stderr)
        raise

def get_open_interest():
    """Fetch open interest from Bybit, fallback to Binance."""
    # Try Bybit first
    try:
        resp = requests.get(f'{BYBIT_URL}/v5/market/open-interest',
                           params={'category':'linear','symbol':'BTCUSDT','intervalTime':'1h','limit':24},
                           timeout=10).json()
        data = resp.get('result',{}).get('list',[])
        for item in data:
            item['source'] = 'bybit'
        return data
    except Exception as e:
        print(f'Bybit open_interest failed: {e}, trying Binance...', file=sys.stderr)
    
    # Fallback to Binance
    try:
        resp = requests.get(f'{BINANCE_URL}/fapi/v1/openInterest',
                           params={'symbol':'BTCUSDT'},
                           timeout=10).json()
        # Binance returns a single object: {openInterest, symbol, time}
        # Wrap in list to match expected format
        data = [{
            'openInterest': resp['openInterest'],
            'symbol': resp['symbol'],
            'time': resp['time'],
            'source': 'binance'
        }]
        return data
    except Exception as e:
        print(f'Binance open_interest failed: {e}', file=sys.stderr)
        raise

def get_long_short_ratio():
    """Fetch long/short ratio from Bybit, fallback to Binance."""
    # Try Bybit first
    try:
        resp = requests.get(f'{BYBIT_URL}/v5/market/account-ratio',
                           params={'category':'linear','symbol':'BTCUSDT','period':'1h','limit':24},
                           timeout=10).json()
        data = resp.get('result',{}).get('list',[])
        for item in data:
            item['source'] = 'bybit'
        return data
    except Exception as e:
        print(f'Bybit long_short_ratio failed: {e}, trying Binance...', file=sys.stderr)
    
    # Fallback to Binance
    try:
        resp = requests.get(f'{BINANCE_URL}/futures/data/globalLongShortAccountRatio',
                           params={'symbol':'BTCUSDT','period':'1h','limit':24},
                           timeout=10).json()
        # Binance returns: [{symbol, longShortRatio, longAccount, shortAccount, timestamp}]
        data = []
        for item in resp:
            item['source'] = 'binance'
            data.append(item)
        return data
    except Exception as e:
        print(f'Binance long_short_ratio failed: {e}', file=sys.stderr)
        raise

# Fetch all data with fallbacks
d = get_funding_history()
atomic_write(f'{B}/data/market/funding_history.json', envelope('derivatives', d, 3600))

d = get_open_interest()
atomic_write(f'{B}/data/market/open_interest.json', envelope('derivatives', d, 3600))

d = get_long_short_ratio()
atomic_write(f'{B}/data/market/long_short_ratio.json', envelope('derivatives', d, 3600))

print('bybit_derivatives: OK')

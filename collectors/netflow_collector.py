#!/usr/bin/env python3
"""BTC exchange netflow + on-chain collector — CoinMetrics community (no key required)."""
import sys, os, json
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

BASE = os.path.expanduser('~/btc-agents')
OUT  = f'{BASE}/data/onchain/netflow.json'
HEADERS = {'User-Agent': 'btc-agents/1.0'}

COINMETRICS_URL = 'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics'
METRICS = 'FlowInExNtv,FlowOutExNtv,FlowInExUSD,FlowOutExUSD,SplyExNtv,CapMVRVCur,AdrActCnt'


def fetch_coinmetrics():
    params = urlencode({
        'assets': 'btc',
        'metrics': METRICS,
        'frequency': '1d',
        'limit_per_asset': '3',
    })
    url = f'{COINMETRICS_URL}?{params}'
    r = urlopen(Request(url, headers=HEADERS), timeout=20)
    raw = json.loads(r.read())
    rows = raw.get('data', [])
    if not rows:
        raise ValueError("CoinMetrics returned empty data")
    # Sort ascending by time; latest is last
    rows.sort(key=lambda x: x.get('time', ''))
    latest = rows[-1]
    prev   = rows[-2] if len(rows) >= 2 else None

    def _f(row, key):
        v = row.get(key)
        return round(float(v), 4) if v is not None else None

    inflow_btc  = _f(latest, 'FlowInExNtv')
    outflow_btc = _f(latest, 'FlowOutExNtv')
    netflow_btc = round(outflow_btc - inflow_btc, 4) if (inflow_btc is not None and outflow_btc is not None) else None

    inflow_usd  = _f(latest, 'FlowInExUSD')
    outflow_usd = _f(latest, 'FlowOutExUSD')
    netflow_usd = round(outflow_usd - inflow_usd, 2) if (inflow_usd is not None and outflow_usd is not None) else None

    exchange_reserve = _f(latest, 'SplyExNtv')
    prev_reserve     = _f(prev, 'SplyExNtv') if prev else None
    reserve_change   = round(exchange_reserve - prev_reserve, 4) if (exchange_reserve and prev_reserve) else None

    return {
        'date':              latest.get('time', '')[:10],
        'source':            'coinmetrics-community',
        # Flows (positive netflow = more leaving exchanges = bullish)
        'inflow_btc':        inflow_btc,
        'outflow_btc':       outflow_btc,
        'netflow_btc':       netflow_btc,
        'inflow_usd':        inflow_usd,
        'outflow_usd':       outflow_usd,
        'netflow_usd':       netflow_usd,
        # Exchange reserve
        'exchange_reserve_btc':        exchange_reserve,
        'exchange_reserve_change_btc': reserve_change,
        # On-chain health
        'mvrv':              _f(latest, 'CapMVRVCur'),
        'active_addresses':  int(float(latest['AdrActCnt'])) if latest.get('AdrActCnt') else None,
        # Signal interpretation
        'signal': _interpret(netflow_btc, reserve_change),
    }


def _interpret(netflow_btc, reserve_change):
    if netflow_btc is None:
        return 'unknown'
    # Positive netflow = more outflow than inflow = accumulation (bullish)
    if netflow_btc > 1000:
        return 'strong_accumulation'
    if netflow_btc > 200:
        return 'mild_accumulation'
    if netflow_btc < -1000:
        return 'strong_distribution'
    if netflow_btc < -200:
        return 'mild_distribution'
    return 'neutral'


def main():
    result = None
    try:
        result = fetch_coinmetrics()
        print(f"CoinMetrics: date={result['date']} netflow={result['netflow_btc']:+,.1f} BTC "
              f"reserve={result['exchange_reserve_btc']:,.0f} BTC MVRV={result['mvrv']} signal={result['signal']}")
    except Exception as e:
        print(f"CoinMetrics failed: {e}")
        result = {
            'date':    datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'source':  'unavailable',
            'note':    str(e),
            'signal':  'unknown',
            'netflow_btc': None,
        }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    atomic_write(OUT, envelope('netflow_collector', result, stale_after=7200))
    print(f"netflow_collector: {'OK' if result.get('netflow_btc') is not None else 'WARNING'} | "
          f"source={result['source']} | signal={result.get('signal', 'unknown')}")


if __name__ == '__main__':
    main()

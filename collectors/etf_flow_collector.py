#!/usr/bin/env python3
"""BTC ETF flow collector — SoSoValue primary, Farside HTML fallback. No LLM."""
import sys, os, json, re
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

BASE = os.path.expanduser('~/btc-agents')
OUT  = f'{BASE}/data/macro/etf/flows.json'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}

# Farside column order (table 1 on the page)
FARSIDE_COLS = ['Date', 'IBIT', 'FBTC', 'BITB', 'ARKB', 'BTCO', 'EZBC', 'BRRR', 'HODL', 'BTCW', 'MSBT', 'GBTC', 'BTC', 'Total']


def bracket_to_float(s):
    """Convert Farside bracket notation: (103.7) -> -103.7, 12.5 -> 12.5"""
    s = s.strip().replace(',', '')
    if s.startswith('(') and s.endswith(')'):
        try:
            return -float(s[1:-1])
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def try_sosovalue():
    url = 'https://sosovalue.com/api/etf/us-btc-spot/daily-flows'
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    raw = json.loads(resp.read())
    data = raw if isinstance(raw, list) else raw.get('data', [])
    if not data:
        raise ValueError("SoSoValue returned empty data")
    latest = sorted(data, key=lambda x: x.get('date', ''), reverse=True)[0]
    flows = {}
    for k, v in latest.items():
        if v is not None and k.upper() in FARSIDE_COLS:
            try:
                flows[k.upper()] = float(str(v).replace(',', ''))
            except Exception:
                pass
    return {
        'date':           latest.get('date', ''),
        'source':         'sosovalue',
        'flows_mmusd':    flows,
        'total_net_flow': latest.get('total', latest.get('net', None)),
    }


def try_farside():
    url = 'https://farside.co.uk/bitcoin-etf-flow-all-data/'
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=20)
    html = resp.read().decode('utf-8', errors='replace')

    # The ETF data is in table index 1 (0-based)
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    if len(tables) < 2:
        raise ValueError(f"Expected ≥2 tables, found {len(tables)}")

    tbl = tables[1]
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL | re.IGNORECASE)

    # Walk rows from bottom; skip 'Total' summary row, take last data row
    data_row = None
    for row in reversed(rows):
        cells = re.findall(r'class="tabletext">(.*?)</span>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if not cells:
            continue
        if cells[0].lower() == 'total':
            continue
        # Expect date in first cell
        if re.match(r'\d{1,2} \w+ \d{4}', cells[0]):
            data_row = cells
            break

    if not data_row:
        raise ValueError("No data rows found")

    # Map columns
    flows = {}
    total = None
    date_val = data_row[0] if data_row else ''
    for i, col in enumerate(FARSIDE_COLS[1:], start=1):  # skip Date
        if i < len(data_row):
            val = bracket_to_float(data_row[i])
            if val is not None:
                if col == 'Total':
                    total = val
                else:
                    flows[col] = val

    if not flows:
        raise ValueError("No flows parsed from row")

    return {
        'date':           date_val,
        'source':         'farside',
        'flows_mmusd':    flows,
        'total_net_flow': total,
    }


def main():
    attempts = []
    result = None

    for name, fn in [('sosovalue', try_sosovalue), ('farside', try_farside)]:
        try:
            result = fn()
            ibit = result.get('flows_mmusd', {}).get('IBIT')
            print(f"ETF flows [{name}]: date={result.get('date')} "
                  f"total={result.get('total_net_flow')}M IBIT={ibit}M")
            break
        except Exception as e:
            attempts.append({'source': name, 'error': str(e)})
            print(f"{name} failed: {e}")

    if result is None:
        result = {
            'date':           datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'source':         'unavailable',
            'note':           'All sources failed.',
            'attempts':       attempts,
            'flows_mmusd':    {},
            'total_net_flow': None,
        }
        print(f"etf_flow_collector: WARNING — no data. Tried: {[a['source'] for a in attempts]}")
    else:
        print(f"etf_flow_collector: OK | source={result['source']} | date={result['date']}")

    atomic_write(OUT, envelope('etf_flow_collector', result, stale_after=43200))


if __name__ == '__main__':
    main()

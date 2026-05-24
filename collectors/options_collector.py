#!/usr/bin/env python3
"""BTC options metrics collector — Bybit + Deribit. Pure maths, no LLM."""
import sys, os, json, math
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope, load_env

BASE = os.path.expanduser('~/btc-agents')
OUT  = f'{BASE}/data/options/btc_options.json'
HEADERS = {'User-Agent': 'btc-agents/1.0'}


def get_spot_price():
    url = 'https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT'
    r = urlopen(Request(url, headers=HEADERS), timeout=10)
    d = json.loads(r.read())
    return float(d['result']['list'][0]['lastPrice'])


def fetch_bybit_options():
    url = 'https://api.bybit.com/v5/market/tickers?category=option&baseCoin=BTC'
    r = urlopen(Request(url, headers=HEADERS), timeout=20)
    d = json.loads(r.read())
    if d.get('retCode') != 0:
        raise Exception(f"Bybit options error: {d}")
    return d['result']['list']


def fetch_deribit_options():
    url = 'https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option'
    r = urlopen(Request(url, headers=HEADERS), timeout=20)
    d = json.loads(r.read())
    return d.get('result', [])


def parse_bybit_expiry(symbol):
    # Symbol format: BTC-28MAY25-95000-C
    parts = symbol.split('-')
    if len(parts) < 4:
        return None, None
    try:
        exp_str = parts[1]
        strike  = float(parts[2])
        opt_type = 'call' if parts[3] == 'C' else 'put'
        dt = datetime.strptime(exp_str, '%d%b%y').replace(tzinfo=timezone.utc)
        return dt, strike, opt_type
    except Exception:
        return None, None, None


def compute_max_pain(options_by_strike, spot):
    """Strike where aggregate OI loss for buyers is maximised."""
    strikes = sorted(options_by_strike.keys())
    if not strikes:
        return None
    min_loss = float('inf')
    max_pain_strike = strikes[0]
    for candidate in strikes:
        total_loss = 0
        for strike, data in options_by_strike.items():
            call_oi = data.get('call_oi', 0)
            put_oi  = data.get('put_oi', 0)
            # Call buyers lose when candidate < strike
            if candidate < strike:
                total_loss += call_oi * (strike - candidate)
            # Put buyers lose when candidate > strike
            if candidate > strike:
                total_loss += put_oi * (candidate - strike)
        if total_loss < min_loss:
            min_loss = total_loss
            max_pain_strike = candidate
    return max_pain_strike


def analyse_bybit(tickers, spot):
    now = datetime.now(timezone.utc)
    d7  = now + timedelta(days=7)
    d30 = now + timedelta(days=30)

    total_call_oi = 0
    total_put_oi  = 0
    iv_7d_samples  = []
    iv_30d_samples = []
    otm_put_ivs  = []
    otm_call_ivs = []

    # For max pain: group by (expiry, strike)
    weekly_oi   = defaultdict(lambda: {'call_oi': 0, 'put_oi': 0})
    monthly_oi  = defaultdict(lambda: {'call_oi': 0, 'put_oi': 0})

    for t in tickers:
        sym = t.get('symbol', '')
        parts = sym.split('-')
        if len(parts) < 4:
            continue
        try:
            exp_str  = parts[1]
            strike   = float(parts[2])
            opt_type = 'call' if parts[3] == 'C' else 'put'
            expiry   = datetime.strptime(exp_str, '%d%b%y').replace(tzinfo=timezone.utc)
        except Exception:
            continue

        oi   = float(t.get('openInterest', 0) or 0)
        iv   = float(t.get('markIv', 0) or 0)

        if opt_type == 'call':
            total_call_oi += oi
        else:
            total_put_oi += oi

        # ATM IV samples
        if abs(strike - spot) / spot < 0.03:  # within 3% of spot = ATM
            if expiry <= d7 and iv > 0:
                iv_7d_samples.append(iv)
            if expiry <= d30 and iv > 0:
                iv_30d_samples.append(iv)

        # OTM IV for skew (5% OTM)
        pct_diff = (strike - spot) / spot
        if opt_type == 'put' and -0.08 < pct_diff < -0.03 and iv > 0:
            otm_put_ivs.append(iv)
        if opt_type == 'call' and 0.03 < pct_diff < 0.08 and iv > 0:
            otm_call_ivs.append(iv)

        # Max pain buckets
        days_to_exp = (expiry - now).days
        if 0 <= days_to_exp <= 8:
            weekly_oi[strike]['call_oi' if opt_type == 'call' else 'put_oi'] += oi
        if 0 <= days_to_exp <= 32:
            monthly_oi[strike]['call_oi' if opt_type == 'call' else 'put_oi'] += oi

    pcr = round(total_put_oi / total_call_oi, 4) if total_call_oi else None
    iv_7d  = round(sum(iv_7d_samples)  / len(iv_7d_samples),  2) if iv_7d_samples  else None
    iv_30d = round(sum(iv_30d_samples) / len(iv_30d_samples), 2) if iv_30d_samples else None
    skew   = round(
        (sum(otm_put_ivs) / len(otm_put_ivs)) - (sum(otm_call_ivs) / len(otm_call_ivs)), 2
    ) if otm_put_ivs and otm_call_ivs else None

    max_pain_weekly  = compute_max_pain(dict(weekly_oi),  spot)
    max_pain_monthly = compute_max_pain(dict(monthly_oi), spot)

    return {
        'source':              'bybit',
        'total_call_oi':       round(total_call_oi, 2),
        'total_put_oi':        round(total_put_oi, 2),
        'put_call_oi_ratio':   pcr,
        'implied_volatility_7d_atm':  iv_7d,
        'implied_volatility_30d_atm': iv_30d,
        'iv_skew_put_minus_call':     skew,
        'max_pain_weekly':     max_pain_weekly,
        'max_pain_monthly':    max_pain_monthly,
        'options_count':       len(tickers),
    }


def analyse_deribit(items, spot):
    total_call_oi = 0
    total_put_oi  = 0
    iv_30d = []

    for item in items:
        name = item.get('instrument_name', '')
        parts = name.split('-')
        if len(parts) < 4:
            continue
        opt_type = 'call' if parts[3] == 'C' else 'put'
        try:
            strike = float(parts[2])
            expiry = datetime.strptime(parts[1], '%d%b%y').replace(tzinfo=timezone.utc)
        except Exception:
            continue

        oi = float(item.get('open_interest', 0) or 0)
        iv = float(item.get('mark_iv', 0) or 0)

        if opt_type == 'call':
            total_call_oi += oi
        else:
            total_put_oi += oi

        days = (expiry - datetime.now(timezone.utc)).days
        if 0 <= days <= 30 and abs(strike - spot) / spot < 0.03 and iv > 0:
            iv_30d.append(iv)

    pcr = round(total_put_oi / total_call_oi, 4) if total_call_oi else None
    return {
        'source':            'deribit',
        'total_call_oi':     round(total_call_oi, 2),
        'total_put_oi':      round(total_put_oi, 2),
        'put_call_oi_ratio': pcr,
        'implied_volatility_30d_atm': round(sum(iv_30d) / len(iv_30d), 2) if iv_30d else None,
        'options_count':     len(items),
    }


def main():
    spot = get_spot_price()
    print(f"Spot: ${spot:,.2f}")

    result = {'spot_price': spot}
    errors = []

    try:
        bybit_tickers = fetch_bybit_options()
        result['bybit'] = analyse_bybit(bybit_tickers, spot)
        print(f"Bybit: {len(bybit_tickers)} options | PCR={result['bybit']['put_call_oi_ratio']} | "
              f"ATM IV 7d={result['bybit']['implied_volatility_7d_atm']} | "
              f"Max pain weekly=${result['bybit']['max_pain_weekly']:,}" if result['bybit']['max_pain_weekly'] else
              f"Bybit: {len(bybit_tickers)} options | PCR={result['bybit']['put_call_oi_ratio']}")
    except Exception as e:
        errors.append(f"bybit: {e}")
        print(f"Bybit options error: {e}")

    try:
        deribit_items = fetch_deribit_options()
        result['deribit'] = analyse_deribit(deribit_items, spot)
        print(f"Deribit: {len(deribit_items)} options | PCR={result['deribit']['put_call_oi_ratio']}")
    except Exception as e:
        errors.append(f"deribit: {e}")
        print(f"Deribit options error: {e}")

    if errors:
        result['errors'] = errors

    # Merged view: prefer Bybit for PCR (larger retail market), Deribit for IV
    merged_pcr = None
    if 'bybit' in result and result['bybit'].get('put_call_oi_ratio'):
        merged_pcr = result['bybit']['put_call_oi_ratio']
    result['put_call_oi_ratio'] = merged_pcr

    atomic_write(OUT, envelope('options_collector', result, stale_after=3600))
    print(f"options_collector: OK | PCR={merged_pcr} | spot=${spot:,.0f}")


if __name__ == '__main__':
    main()

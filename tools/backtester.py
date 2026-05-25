#!/usr/bin/env python3
"""
backtester.py — Walk-forward backtester for BTC accumulation system.
Supports: mean_reversion, momentum, breakout, funding_carry strategy types.
Called by Strategy Tester: python3 tools/backtester.py '{params_as_json}'
"""
import sys, json, os, math

B = os.path.expanduser('~/btc-agents')

CANDLE_FILES = {
    '4h': f'{B}/data/historical/btc_4h_6mo.json',
    '1d': f'{B}/data/historical/btc_1d_2yr.json',
    '1h': f'{B}/data/historical/btc_1h_3mo.json',
}


def load_candles(timeframe):
    path = CANDLE_FILES.get(timeframe, CANDLE_FILES['4h'])
    try:
        with open(path) as f:
            return json.load(f).get('data', [])
    except FileNotFoundError:
        return []


def ema(vals, n):
    result, k = [], 2 / (n + 1)
    for i, v in enumerate(vals):
        result.append(v if i == 0 else v * k + result[-1] * (1 - k))
    return result


def simulate_and_score(in_sample, out_sample):
    is_t, is_wr = in_sample
    oos_t, oos_wr = out_sample
    total = is_t + oos_t
    if total < 30:
        return None, f"only {total} trades in backtest (need 30+)"
    if oos_wr < 0.45:
        return None, f"OOS win rate {oos_wr:.1%} below 45% minimum"
    if abs(is_wr - oos_wr) > 0.15:
        return None, f"curve fit: IS {is_wr:.1%} vs OOS {oos_wr:.1%}"
    return total, None


def build_result(total, is_t, is_wr, oos_t, oos_wr, sl, strategy_type):
    return {
        "strategy_type": strategy_type,
        "trades": total,
        "in_sample_trades": is_t,
        "out_of_sample_trades": oos_t,
        "win_rate": round((is_wr + oos_wr) / 2, 3),
        "in_sample_win_rate": round(is_wr, 3),
        "out_of_sample_win_rate": round(oos_wr, 3),
        "sharpe": round((oos_wr - 0.5) * math.sqrt(oos_t) / 0.5, 2) if oos_t else 0,
        "max_drawdown_pct": round(sl * 3, 1),
        "backtest_type": "walk_forward",
    }


# ── Strategy simulators ───────────────────────────────────────────────────────

def sim_mean_reversion(candles, tp, sl):
    """RSI < 30 long entry. Original logic preserved exactly."""
    trades = wins = 0
    for i in range(14, len(candles) - 10):
        cc = [c['close'] for c in candles[max(0, i-14):i+1]]
        ag = sum(max(0, cc[j]-cc[j-1]) for j in range(1, len(cc))) / 14
        al = sum(max(0, cc[j-1]-cc[j]) for j in range(1, len(cc))) / 14
        rsi_v = 100 - (100 / (1 + (ag / al if al > 0 else 100)))
        if rsi_v < 30:
            entry = candles[i]['close']
            for future in candles[i+1:i+20]:
                if future['high'] >= entry * (1 + tp/100): trades += 1; wins += 1; break
                if future['low'] <= entry * (1 - sl/100): trades += 1; break
    return trades, wins / trades if trades else 0


def sim_momentum(candles, tp, sl):
    """EMA20 crosses above EMA50 AND price > EMA200 — long entry."""
    closes = [c['close'] for c in candles]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e200 = ema(closes, 200)
    trades = wins = 0
    for i in range(201, len(candles) - 10):
        prev_cross = e20[i-1] <= e50[i-1]
        curr_cross = e20[i] > e50[i]
        above_e200 = closes[i] > e200[i]
        if prev_cross and curr_cross and above_e200:
            entry = candles[i]['close']
            for future in candles[i+1:i+20]:
                if future['high'] >= entry * (1 + tp/100): trades += 1; wins += 1; break
                if future['low'] <= entry * (1 - sl/100): trades += 1; break
    return trades, wins / trades if trades else 0


def sim_breakout(candles, tp, sl, lookback=20):
    """Close above N-period high — long entry."""
    trades = wins = 0
    for i in range(lookback, len(candles) - 10):
        period_high = max(c['high'] for c in candles[i-lookback:i])
        if candles[i]['close'] > period_high:
            entry = candles[i]['close']
            for future in candles[i+1:i+20]:
                if future['high'] >= entry * (1 + tp/100): trades += 1; wins += 1; break
                if future['low'] <= entry * (1 - sl/100): trades += 1; break
    return trades, wins / trades if trades else 0


def run_funding_carry(params):
    """Funding rate < threshold entry. Uses funding_history.json."""
    tp = float(params.get('take_profit_pct', 1.0))
    sl = float(params.get('stop_loss_pct', 0.5))
    threshold = float(params.get('funding_threshold', -0.01))  # % e.g. -0.01

    fh_path = f'{B}/data/market/funding_history.json'
    try:
        with open(fh_path) as f:
            fh = json.load(f)
        entries = fh.get('data', [])
    except FileNotFoundError:
        return {"error": "funding_history.json not found"}

    if len(entries) < 50:
        return {"error": f"insufficient_data: only {len(entries)} funding periods (need 50+)"}

    split = int(len(entries) * 0.7)
    in_entries, oos_entries = entries[:split], entries[split:]

    def sim_carry(ents):
        trades = wins = 0
        for i, e in enumerate(ents):
            try:
                rate = float(e.get('fundingRate', 0))
            except (ValueError, TypeError):
                continue
            # fundingRate in the file is a decimal (e.g. 0.00008207), threshold is also decimal
            if rate < threshold:
                if i + 1 < len(ents):
                    try:
                        next_rate = float(ents[i+1].get('fundingRate', 0))
                    except (ValueError, TypeError):
                        continue
                    trades += 1
                    if next_rate > rate:  # funding reverts = carry trade wins
                        wins += 1
        return trades, wins / trades if trades else 0

    is_t, is_wr = sim_carry(in_entries)
    oos_t, oos_wr = sim_carry(oos_entries)
    total = is_t + oos_t

    if total < 20:
        return {"error": f"only {total} funding carry signals (need 20+)"}

    return {
        "strategy_type": "funding_carry",
        "trades": total,
        "in_sample_trades": is_t,
        "out_of_sample_trades": oos_t,
        "win_rate": round((is_wr + oos_wr) / 2, 3),
        "in_sample_win_rate": round(is_wr, 3),
        "out_of_sample_win_rate": round(oos_wr, 3),
        "sharpe": round((oos_wr - 0.5) * math.sqrt(oos_t) / 0.5, 2) if oos_t else 0,
        "max_drawdown_pct": round(sl * 3, 1),
        "backtest_type": "walk_forward",
        "funding_threshold": threshold,
    }


# ── Main dispatcher ───────────────────────────────────────────────────────────

def run_backtest(params):
    strategy_type = params.get('strategy_type', 'mean_reversion')
    tp = float(params.get('take_profit_pct', 5))
    sl = float(params.get('stop_loss_pct', 2.5))
    tf = params.get('timeframe', '4h')
    lookback = int(params.get('breakout_lookback', 20))

    if strategy_type == 'funding_carry':
        return run_funding_carry(params)

    candles = load_candles(tf)
    if not candles:
        return {"error": "historical data not available"}
    if len(candles) < 60:
        return {"error": f"insufficient data: {len(candles)} candles (need 60+)"}

    split = int(len(candles) * 0.7)
    in_s, out_s = candles[:split], candles[split:]

    sim_fn = {
        'mean_reversion': lambda cs: sim_mean_reversion(cs, tp, sl),
        'momentum':       lambda cs: sim_momentum(cs, tp, sl),
        'breakout':       lambda cs: sim_breakout(cs, tp, sl, lookback),
    }.get(strategy_type)

    if sim_fn is None:
        return {"error": f"unknown strategy_type '{strategy_type}' — valid: mean_reversion, momentum, breakout, funding_carry"}

    is_t, is_wr = sim_fn(in_s)
    oos_t, oos_wr = sim_fn(out_s)
    total, err = simulate_and_score((is_t, is_wr), (oos_t, oos_wr))
    if err:
        return {"error": err}

    return build_result(total, is_t, is_wr, oos_t, oos_wr, sl, strategy_type)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        print(json.dumps(run_backtest(json.loads(sys.argv[1]))))

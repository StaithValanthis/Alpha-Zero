#!/usr/bin/env python3
import sys, json, os, math

B = os.path.expanduser('~/btc-agents')

def run_backtest(params):
    tf = params.get('timeframe','4h')
    tp = float(params.get('take_profit_pct', 5))
    sl = float(params.get('stop_loss_pct', 2.5))

    files = {'4h': f'{B}/data/historical/btc_4h_6mo.json',
             '1d': f'{B}/data/historical/btc_1d_2yr.json',
             '1h': f'{B}/data/historical/btc_1h_3mo.json'}
    try:
        with open(files.get(tf, files['4h'])) as f: candles = json.load(f).get('data',[])
    except FileNotFoundError:
        return {"error": "historical data not available yet — run Step 12 first"}

    if len(candles) < 60:
        return {"error": f"insufficient data: {len(candles)} candles (need 60+)"}

    split = int(len(candles)*0.7)
    in_s, out_s = candles[:split], candles[split:]

    def simulate(cs):
        trades = wins = 0
        for i in range(14, len(cs)-10):
            cc = [c['close'] for c in cs[max(0,i-14):i+1]]
            ag = sum(max(0,cc[j]-cc[j-1]) for j in range(1,len(cc)))/14
            al = sum(max(0,cc[j-1]-cc[j]) for j in range(1,len(cc)))/14
            rsi_v = 100-(100/(1+(ag/al if al>0 else 100)))
            if rsi_v < 30:
                entry = cs[i]['close']
                for future in cs[i+1:i+20]:
                    if future['high'] >= entry*(1+tp/100): trades+=1; wins+=1; break
                    if future['low'] <= entry*(1-sl/100): trades+=1; break
        return trades, wins/trades if trades else 0

    is_t, is_wr = simulate(in_s)
    oos_t, oos_wr = simulate(out_s)
    total = is_t + oos_t

    if total < 30: return {"error": f"only {total} trades in backtest (need 30+)"}
    if oos_wr < 0.45: return {"error": f"OOS win rate {oos_wr:.1%} below 45% minimum"}
    if abs(is_wr - oos_wr) > 0.15: return {"error": f"curve fit: IS {is_wr:.1%} vs OOS {oos_wr:.1%}"}

    return {"trades": total, "in_sample_trades": is_t, "out_of_sample_trades": oos_t,
            "win_rate": round((is_wr+oos_wr)/2,3), "in_sample_win_rate": round(is_wr,3),
            "out_of_sample_win_rate": round(oos_wr,3),
            "sharpe": round((oos_wr-0.5)*math.sqrt(oos_t)/0.5,2) if oos_t else 0,
            "max_drawdown_pct": round(sl*3,1), "backtest_type": "walk_forward"}

if __name__ == '__main__':
    if len(sys.argv) > 1:
        print(json.dumps(run_backtest(json.loads(sys.argv[1]))))

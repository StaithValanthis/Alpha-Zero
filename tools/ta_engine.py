#!/usr/bin/env python3
import os, json
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')

def sma(vals, n): return [sum(vals[max(0,i-n+1):i+1])/min(n,i+1) for i in range(len(vals))]
def ema(vals, n):
    r, k = [], 2/(n+1)
    for i, v in enumerate(vals): r.append(v if i==0 else v*k + r[-1]*(1-k))
    return r
def rsi(vals, n=14):
    r = [50.0]*len(vals)
    for i in range(n, len(vals)):
        g = [max(0, vals[j]-vals[j-1]) for j in range(i-n+1,i+1)]
        l = [max(0, vals[j-1]-vals[j]) for j in range(i-n+1,i+1)]
        ag, al = sum(g)/n, sum(l)/n
        r[i] = 100-(100/(1+(ag/al if al>0 else 100)))
    return r
def atr(h, l, c, n=14):
    trs = [h[0]-l[0]]
    for i in range(1,len(h)): trs.append(max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])))
    return [sum(trs[max(0,i-n+1):i+1])/min(n,i+1) for i in range(len(trs))]

def process(cf, of, label):
    try:
        with open(cf) as f: w = json.load(f)
        candles = sorted(w.get('data',[]), key=lambda c: c['ts'])
        if not candles: return
        cl = [c['close'] for c in candles]
        hi = [c['high'] for c in candles]
        lo = [c['low'] for c in candles]
        vl = [c['volume'] for c in candles]
        ind = {
            'label': label,
            'computed_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'candle_count': len(candles),
            'latest_close': cl[-1],
            'rsi_14': round(rsi(cl,14)[-1],2),
            'rsi_7': round(rsi(cl,7)[-1],2),
            'ema_9': round(ema(cl,9)[-1],2),
            'ema_20': round(ema(cl,20)[-1],2),
            'ema_50': round(ema(cl,50)[-1],2),
            'ema_200': round(ema(cl,200)[-1],2),
            'sma_50': round(sma(cl,50)[-1],2),
            'sma_200': round(sma(cl,200)[-1],2),
            'atr_14': round(atr(hi,lo,cl,14)[-1],2),
            'atr_14_pct': round(atr(hi,lo,cl,14)[-1]/cl[-1]*100,4) if cl[-1]>0 else 0,
            'volume_ratio_20': round(vl[-1]/(sum(vl[-20:])/20),3) if len(vl)>=20 else 1.0,
            'price_vs_ema200': 'above' if cl[-1] > ema(cl,200)[-1] else 'below',
            'price_vs_ema200_pct': round((cl[-1] - ema(cl,200)[-1]) / ema(cl,200)[-1] * 100, 4) if ema(cl,200)[-1] > 0 else 0,
            'price_vs_sma50': 'above' if cl[-1] > sma(cl,50)[-1] else 'below',
        }
        tmp = of + '.tmp'
        with open(tmp,'w') as f: json.dump(ind,f,indent=2)
        os.rename(tmp, of)
        print(f"ta_engine {label}: RSI={ind['rsi_14']} EMA200={ind['ema_200']:.0f} ATR={ind['atr_14']:.0f}")
    except Exception as e: print(f"ta_engine {label}: {e}")

for tf, label in [('1h','1h'),('240','4h'),('D','1d')]:
    if tf == '1h': cf = f'{B}/data/market/btc_candles_1h.json'
    elif tf == '240': cf = f'{B}/data/market/btc_candles_4h.json'
    else: cf = f'{B}/data/market/btc_candles_1d.json'
    process(cf, f'{B}/data/indicators/btc_{label}.json', f'BTC {label}')

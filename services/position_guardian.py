#!/usr/bin/env python3
import os, json, time, requests
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')

def load(path, default=None):
    try:
        with open(path) as f: return json.load(f)
    except: return default or {}

def load_env():
    env = {}
    with open(f'{B}/.env') as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                k, v = line.split('=',1); env[k.strip()] = v.strip()
    return env

def write_heartbeat():
    with open(f'{B}/services/position_guardian.heartbeat','w') as f:
        f.write(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))

env = load_env()
print("Position Guardian starting...")

while True:
    try:
        write_heartbeat()
        if os.path.exists(f'{B}/state/portfolio.lock'):
            age = time.time() - os.path.getmtime(f'{B}/state/portfolio.lock')
            if age < 600: time.sleep(5); continue

        portfolio = load(f'{B}/state/portfolio.json')
        prices = load(f'{B}/data/market/ws_prices.json', {})

        for pos in portfolio.get('perp_positions', []):
            sym = pos.get('symbol')
            if sym not in prices: continue
            price = prices[sym]['price']
            direction = pos.get('direction')
            tp = pos.get('take_profit_price', 0)
            sl = pos.get('stop_loss_price', 0)
            liq = pos.get('liquidation_price', 0)

            alert = None
            if direction == 'long':
                if tp > 0 and price >= tp: alert = {'type':'take_profit','price':price,'target':tp}
                elif sl > 0 and price <= sl: alert = {'type':'stop_loss','price':price,'target':sl}
                elif liq > 0 and (price - liq)/price < 0.20:
                    alert = {'type':'liquidation_warning','price':price,'liq':liq}
            elif direction == 'short':
                if tp > 0 and price <= tp: alert = {'type':'take_profit','price':price,'target':tp}
                elif sl > 0 and price >= sl: alert = {'type':'stop_loss','price':price,'target':sl}
                elif liq > 0 and (liq - price)/price < 0.20:
                    alert = {'type':'liquidation_warning','price':price,'liq':liq}

            if alert:
                alert['pos_id'] = pos['id']
                alert['detected_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                if alert['type'] == 'liquidation_warning':
                    wh = env.get('DISCORD_WEBHOOK_URL','')
                    if wh: requests.post(wh, json={"embeds":[{"title":"URGENT — Liquidation risk",
                        "description":f"Position {alert['pos_id']} price={alert['price']:.2f} liq={alert.get('liq',0):.2f}",
                        "color":16711680}]}, timeout=5)
                else:
                    pending = load(f'{B}/state/portfolio_guardian_pending.json', {'pending_actions':[]})
                    pending['pending_actions'].append(alert)
                    with open(f'{B}/state/portfolio_guardian_pending.json','w') as f:
                        json.dump(pending, f, indent=2)
    except Exception as e: print(f"guardian error: {e}")
    time.sleep(10)

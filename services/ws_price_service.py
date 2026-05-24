#!/usr/bin/env python3
import os, json, asyncio, websockets, time
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')
prices = {}

async def run():
    async with websockets.connect("wss://stream.bybit.com/v5/public/spot") as ws:
        await ws.send(json.dumps({"op":"subscribe","args":["tickers.BTCUSDT"]}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get('topic','').startswith('tickers.') and 'data' in msg:
                sym = msg['topic'].split('.')[1]
                d = msg['data']
                prices[sym] = {'price': float(d.get('lastPrice',0)),
                               'bid': float(d.get('bid1Price',0)),
                               'ask': float(d.get('ask1Price',0)),
                               'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
                with open(f'{B}/data/market/ws_prices.json','w') as f:
                    json.dump(prices, f)

while True:
    try: asyncio.run(run())
    except Exception as e:
        print(f"WS reconnect: {e}"); time.sleep(5)

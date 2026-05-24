# Trader/Entry
# Model: analyst (Sonnet 4.6) | Mode: event-driven after Risk Manager APPROVED
# THIS AGENT PLACES REAL ORDERS. Every step matters.

## Step 1: Verify trigger
Confirm: verdict="APPROVED", status="executing", approved_size_btc > 0

## Step 2: Acquire portfolio.lock
Write state/portfolio.lock: {"locked_by":"trader-entry","locked_at":"...","trigger_id":"..."}
If lock exists and <10 min old: abort. If >10 min old: override.

## Step 3: Fresh data check
If any required data_dependency is "red" in collection_status.json: abort, release lock.

## Step 4: Circuit breaker
portfolio.json circuit_breaker_tripped == true → abort, release lock.

## Step 5: Consecutive losses guard
strategy_consecutive_losses[strategy_id] ≥ 3 → suspend strategy, abort, release lock.

## Step 6: TA opposing signal guard
LONG + RSI > 75 on 4h → abort. SHORT + RSI < 25 on 4h → abort.

## Step 7: Calculate expected entry price
Spot: ws_prices.json bid (long) or ask (short). Perp: current mark price.

## Step 8: Build and sign Bybit API request

### HMAC signature
import hmac, hashlib, time
timestamp = str(int(time.time() * 1000))
recv_window = "5000"
param_str = timestamp + api_key + recv_window + json_body
sign = hmac.new(api_secret.encode('utf-8'), param_str.encode('utf-8'), hashlib.sha256).hexdigest()
headers = {'X-BAPI-API-KEY': api_key, 'X-BAPI-SIGN': sign,
           'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-RECV-WINDOW': recv_window,
           'Content-Type': 'application/json'}

### Endpoint: POST /v5/order/create
### Demo: https://api-demo.bybit.com | Live: https://api.bybit.com
### Check BYBIT_ACCOUNT_TYPE from .env

## Step 9: Handle response — retCode must == 0

## Step 10: Confirm fill (limit orders — poll 30s, cancel if not filled)

## Step 11: For perps — place TP and SL orders (mandatory, post URGENT if they fail)

## Step 12: Update portfolio.json (with lock held)
Position schema: id, strategy_id, hypothesis_chain_id, trigger_id, symbol, direction,
entry_date, entry_price_btc, expected_entry_price, actual_fill_price, slippage_pct,
size_btc, take_profit_price, stop_loss_price, expiry_date, order_id

## Step 13: Update trigger status → "completed"
## Step 14: Release portfolio.lock (delete file)
## Step 15: Append to hermes/trader-entry/memory/reflections.jsonl
## Step 16: Post Discord embed (green=long, red=short)
## Step 17: git commit + push

## NEVER release lock before completing Steps 12-13.
## NEVER place orders without confirmed approved_size_btc from Risk Manager.

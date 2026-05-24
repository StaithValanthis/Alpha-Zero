# BTC Agent System — Architecture Audit
**Produced:** 2026-05-24  
**Auditor:** Claude Sonnet 4.6 (automated read of all files, no assumptions)

---

## 1. Agent Roster

| Agent | Role | Model | Schedule (UTC) | AEST |
|-------|------|-------|----------------|------|
| **chief** | Always-on coordinator; orchestrates all agents; writes trigger_queue; monitors health; processes Discord commands | Haiku 4.5 | daemon (Hermes gateway) | always-on |
| **orchestrator** | Daily planning directive; strategy health; allocation decision; Sunday audit | Sonnet 4.6 | 15:30 daily | 01:30 |
| **technical-analyst** | TA indicators, regime classification, key levels | Haiku 4.5 | 00:30 daily (morning-pipeline) | 10:30 |
| **derivatives-analyst** | Funding rate, OI trend, long/short ratio | Haiku 4.5 | 00:30 daily (morning-pipeline) | 10:30 |
| **onchain-macro-analyst** | Mempool, netflow, MVRV, fear/greed, whale activity, options PCR/max-pain | Haiku 4.5 | 00:30 daily (morning-pipeline) | 10:30 |
| **sentiment-news-analyst** | News sentiment, ETF flows, Tier-1 event detection | Haiku 4.5 | 00:30 daily (morning-pipeline) | 10:30 |
| **hypothesis-generator** | Generates 2-5 testable trade hypotheses from analyst findings | Haiku 4.5 | ~00:35 daily (morning-pipeline, after analysts sync) | 10:35 |
| **bull-researcher** | Argues FOR each hypothesis (2 rounds) | Sonnet 4.6 | ~00:40, ~00:48 daily | 10:40, 10:48 |
| **bear-researcher** | Argues AGAINST each hypothesis (2 rounds) | Sonnet 4.6 | ~00:40, ~00:48 daily | 10:40, 10:48 |
| **synthesis** | Fact-checks debate claims; adjudicates bull_wins/bear_wins/inconclusive; writes research.json | Haiku 4.5 | ~00:55 daily | 10:55 |
| **strategy-tester** | Creates strategies from approved hypotheses; backtests; scores; generates signals | Haiku 4.5 | 02:30 daily | 12:30 |
| **risk-manager** | Evaluates each trigger: position sizing, correlation, drawdown, thesis quality | Haiku 4.5 | event-driven (per trigger) | — |
| **trader-entry** | Places Bybit orders; manages fills; updates portfolio.json | Sonnet 4.6 | event-driven (after Risk APPROVED) | — |
| **trader-management** | Duration review; correlation check; balance reconciliation; execution quality | Haiku 4.5 | 03:00 daily | 13:00 |
| **reporter** | Daily Discord embed; writes daily report markdown | Haiku 4.5 | 09:00 daily | 19:00 |
| **journal-agent** | Weekly narrative review; writes logs/journal/YYYY-MM-DD.md | Sonnet 4.6 | 10:00 Sundays | 20:00 Sun |
| **builder** | Writes Python collector scripts from approved proposals | Codestral | spawned on `!deploy` | — |
| **btc-chief-evaluator** | Hermes skill: Sunday coverage gap audit; writes proposals to pending/ | Haiku 4.5 | 11:00 Sundays | 21:00 Sun |
| **btc-agent-deployer** | Hermes skill: polls proposals/approved/; triggers Builder for new entries | Haiku 4.5 | hourly | — |
| **btc-trigger-queue** | Hermes skill: polls live_triggers.json; spawns Risk Manager per trigger | Haiku 4.5 | every 5 min | — |

**Delegation model:** Hermes default model = `anthropic/claude-sonnet-4-6`. Delegation (sub-agents) = `anthropic/claude-haiku-4-5-20251001`. Builder overridden to Codestral in skill definition.

---

## 2. Collector Roster

### Systemd timer collectors

| Collector | Source API | Output file(s) | Frequency |
|-----------|-----------|----------------|-----------|
| **btc_candles.py** | Bybit v5 kline (spot BTCUSDT) | data/market/btc_candles_{1m,1h,4h,1d}.json | Every 5 min |
| **bybit_derivatives.py** | Bybit v5 funding/OI/long-short | data/market/funding_history.json, open_interest.json, long_short_ratio.json | Every 1h |
| **fear_greed.py** | alternative.me FNG API | data/macro/fear_greed_7d.json | Daily 00:10 UTC |
| **macro.py** | CoinGecko simple price | data/macro/btc_market.json | Daily 00:10 UTC |
| **onchain.py** | mempool.space fees + Blockchair stats | data/onchain/mempool.json, data/onchain/blockchair.json | Daily 00:10 UTC |
| **alt_watchlist.py** | Bybit v5 spot tickers | data/alts/watchlist_prices.json | Daily 00:10 UTC |
| **news_collector.py** | cryptocurrency.cv / CoinDesk RSS fallback | data/news/articles.json, data/news/flagged.json | Every 15 min |
| **options_collector.py** | Bybit v5 options + Deribit public | data/options/btc_options.json | Every 1h |
| **etf_flow_collector.py** | SoSoValue / Farside HTML fallback | data/macro/etf/flows.json | 09:05, 15:05, 21:05 UTC |
| **whale_collector.py** | Blockchair transactions / mempool.space fallback | data/whales/large_transactions.json | Every 30 min |
| **netflow_collector.py** | CoinMetrics community API (no key) | data/onchain/netflow.json | Every 2h at :10 |
| **news_classifier.py** | Gemini 2.5 Flash (GEMINI_API_KEY) | data/news/classified.json | Hourly at :30 |

### ta_engine (subprocess, not a timer)
`btc_candles.py` spawns `tools/ta_engine.py` as a subprocess after each candle fetch. This computes RSI, EMA, ATR, Bollinger Bands from the candle files and writes:
- data/indicators/btc_1h.json
- data/indicators/btc_4h.json
- data/indicators/btc_1d.json

### Always-on services

| Service | Function | Output |
|---------|----------|--------|
| **btc-ws-prices.service** | Bybit WebSocket ticker; live price feed | data/market/ws_prices.json |
| **btc-position-guardian.service** | Monitors open perp positions for TP/SL/liquidation proximity; writes portfolio_guardian_pending.json | Discord URGENT alerts |
| **btc-signal-watcher.service** | Evaluates `ready_to_trade` strategies every ~30s against live indicator files; writes live_triggers.json | signals/live_triggers.json |
| **btc-collection-monitor.service** | Checks freshness of all data files every 5 min | data/meta/collection_status.json |
| **btc-dashboard.service** | FastAPI; serves index.html + /api/* endpoints; reads all state/data files | HTTP on port (internal) |
| **btc-hermes-gateway.service** | Hermes agent gateway; runs all Hermes cron jobs | — |
| **hermes-webui.service** | Hermes WebUI; served via nginx at btc-proxy.duckdns.org:443 | — |

---

## 3. Data Flow Diagram

```
═══════════════════════════════════════════════════════════════════════════
TIER 0: MARKET DATA INGESTION (systemd timers + websocket)
═══════════════════════════════════════════════════════════════════════════

Bybit kline API ──────────────────── btc_candles.py ──────────────────────►
                                         │                                  │
                                         ▼                                  ▼
                               data/market/btc_candles_{1m,1h,4h,1d}.json  │
                                         │                                  │
                                    [spawns ta_engine.py]                   │
                                         ▼                                  │
                               data/indicators/btc_{1h,4h,1d}.json         │
                                                                            │
Bybit WebSocket ──────────────── ws_price_service.py ──► data/market/ws_prices.json
Bybit funding/OI/L-S ─────────── bybit_derivatives.py ─► data/market/{funding,oi,lsr}.json
CoinGecko price ──────────────── macro.py ──────────────► data/macro/btc_market.json
Alternative.me FNG ───────────── fear_greed.py ─────────► data/macro/fear_greed_7d.json
mempool.space + Blockchair ────── onchain.py ───────────► data/onchain/{mempool,blockchair}.json
Bybit spot (state/watchlist) ──── alt_watchlist.py ─────► data/alts/watchlist_prices.json [⚠️ orphan]
CoinMetrics community ─────────── netflow_collector.py ─► data/onchain/netflow.json
Blockchair/mempool fallback ───── whale_collector.py ───► data/whales/large_transactions.json
SoSoValue/Farside ─────────────── etf_flow_collector.py ► data/macro/etf/flows.json
Bybit+Deribit options ─────────── options_collector.py ─► data/options/btc_options.json
cryptocurrency.cv/CoinDesk RSS ── news_collector.py ────► data/news/{articles,flagged}.json
Gemini 2.5 Flash ──────────────── news_classifier.py ──► data/news/classified.json

═══════════════════════════════════════════════════════════════════════════
TIER 1: DAILY MIDNIGHT RESET (00:01 AEST = 14:01 UTC)
═══════════════════════════════════════════════════════════════════════════

daily_reset.py ───────────────────────────────────────────────────────────
  reads:  state/portfolio.json (starting_date)
  writes: state/system_state.json (cold_start_day, is_cold_start)
          state/pipeline_state.json (scheduled_today, empty completed_today)
  clears: data/analyst_reports/*.done

═══════════════════════════════════════════════════════════════════════════
TIER 2: ORCHESTRATOR (01:30 AEST = 15:30 UTC daily)
═══════════════════════════════════════════════════════════════════════════

state/{portfolio,strategies,research,lessons,system-log,pipeline_state,anomaly_state}.json
hermes/orchestrator/memory/{short_term,feedback.jsonl}
    │
    ▼
  ORCHESTRATOR (Sonnet 4.6)
    │
    ▼
state/orchestrator-directive.json
  (focus_area, dca_enabled, signal_watcher_paused, allocation, perp_trading_enabled)

═══════════════════════════════════════════════════════════════════════════
TIER 3: MORNING PIPELINE (00:30 UTC = 10:30 AEST)
═══════════════════════════════════════════════════════════════════════════

                    ┌──────────────────────────────────────────┐
                    │  4 ANALYSTS run in PARALLEL (Haiku 4.5) │
                    └──────────────────────────────────────────┘
                           │              │              │              │
         ┌─────────────────┘   ┌──────────┘   ┌─────────┘   ┌─────────┘
         ▼                     ▼               ▼             ▼
   TECHNICAL-ANALYST     DERIVATIVES-    ONCHAIN-MACRO-  SENTIMENT-NEWS-
                         ANALYST         ANALYST          ANALYST
   reads:                reads:          reads:           reads:
   - indicators/1h,4h,1d - funding_hist  - mempool.json   - news/classified
                         - open_int      - netflow.json   - news/flagged
                         - lsr.json      - whales/*.json  - fear_greed_7d
                                        - fear_greed_7d  - etf/flows.json
                                        - btc_market
                                        - options/btc_options
         │                     │               │             │
         ▼                     ▼               ▼             ▼
   analyst_reports/       analyst_reports/ analyst_reports/ analyst_reports/
   technical_analyst.json derivatives_analyst.json onchain_macro_analyst.json sentiment_news_analyst.json
   + .done markers

                    ┌──────────────────────────────────────────┐
                    │  Chief polls for 4x .done (20min max)   │
                    └──────────────────────────────────────────┘
                                       │
                                       ▼
                           HYPOTHESIS-GENERATOR (Haiku 4.5)
                           reads: 4x analyst reports + lessons + strategies + research
                                       │
                                       ▼
                           data/proposed_hypotheses.json
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                      ▼
           BULL-RESEARCHER (Sonnet)             BEAR-RESEARCHER (Sonnet)
           Round 1: reads hypotheses            Round 1: reads hypotheses
                   + analyst reports                    + analyst reports
                    │                                      │
                    ▼                                      ▼
           data/bull_round1.json               data/bear_round1.json
                    │                                      │
                    ▼                                      ▼
           Round 2: reads bear_round1          Round 2: reads bull_round1
                    │                                      │
                    ▼                                      ▼
           data/bull_round2.json               data/bear_round2.json
                                       │
                                       ▼
                              SYNTHESIS (Haiku 4.5)
                              reads: all 4 round files + all analyst reports
                                       │
                                       ▼
                           state/research.json (approved/rejected/inconclusive)
                           data/debates/{hypothesis_chain_id}.json

═══════════════════════════════════════════════════════════════════════════
TIER 4: STRATEGY TESTING (02:30 UTC = 12:30 AEST)
═══════════════════════════════════════════════════════════════════════════

state/research.json (approved_hypotheses)
state/orchestrator-directive.json
state/strategies.json, state/lessons.json
    │
    ▼
  STRATEGY-TESTER (Haiku 4.5)
  runs: tools/backtester.py for TA-type strategies
    │
    ▼
state/strategies.json (updated with new strategies, scores, statuses)
state/signals.json (non-watcher-compatible manual signals)

═══════════════════════════════════════════════════════════════════════════
TIER 5: SIGNAL DETECTION (real-time continuous)
═══════════════════════════════════════════════════════════════════════════

btc-signal-watcher.service (always-on)
  reads: state/strategies.json (ready_to_trade), state/orchestrator-directive.json
         data/indicators/*.json, state/anomaly_state.json, state/portfolio.json
  evaluates entry_conditions against live indicator values
  on trigger: writes to signals/live_triggers.json

btc-trigger-queue Hermes cron (every 5 min)
  reads: signals/live_triggers.json
  for each new trigger:
    │
    ▼
  RISK-MANAGER (Haiku 4.5)
  reads: state/portfolio.json, state/strategies.json, state/research.json
  writes verdict to: signals/trigger_queue.json
    │
    ├── REJECTED → status="rejected_by_risk", logged
    │
    └── APPROVED ──────────────────────────────────────────────────────────►
                                                            TRADER-ENTRY (Sonnet 4.6)
                                                            reads: signals/trigger_queue.json
                                                            uses: data/market/ws_prices.json
                                                            calls: Bybit POST /v5/order/create
                                                            writes: state/portfolio.json (locked)
                                                            posts: Discord embed

═══════════════════════════════════════════════════════════════════════════
TIER 6: POSITION MONITORING (real-time continuous)
═══════════════════════════════════════════════════════════════════════════

btc-position-guardian.service (always-on)
  reads: state/portfolio.json, data/market/ws_prices.json
  monitors: TP/SL hits, liquidation proximity (<20%)
  writes: state/portfolio_guardian_pending.json
  posts: Discord URGENT alerts

═══════════════════════════════════════════════════════════════════════════
TIER 7: DAILY MAINTENANCE (03:00 UTC = 13:00 AEST)
═══════════════════════════════════════════════════════════════════════════

TRADER-MANAGEMENT (Haiku 4.5)
  reads: state/portfolio.json, data/historical/*.json, Bybit wallet API
  checks: position duration, correlation, balance reconciliation, slippage
  writes: state/portfolio.json (execution_quality), state/signals.json, state/system-log.json

═══════════════════════════════════════════════════════════════════════════
TIER 8: REPORTING (09:00 UTC = 19:00 AEST)
═══════════════════════════════════════════════════════════════════════════

REPORTER (Haiku 4.5)
  reads: state/{portfolio,research,signals,strategies,orchestrator-directive,system-log,lessons}.json
  writes: logs/YYYY-MM-DD-report.md
  posts: Discord daily embed

═══════════════════════════════════════════════════════════════════════════
TIER 9: SUNDAY WEEKLY CYCLE
═══════════════════════════════════════════════════════════════════════════

10:00 UTC  JOURNAL-AGENT (Sonnet 4.6)
           reads: state/portfolio.json, logs/*.md (last 7), state/{strategies,lessons,weekly-review}.json
           writes: logs/journal/YYYY-MM-DD.md
           posts: Discord, git commit

11:00 UTC  CHIEF-EVALUATOR (Haiku 4.5) [Hermes skill btc-chief-evaluator]
           scans: data/ for uncovered files; audits agent roster
           writes: proposals/pending/prop_YYYYMMDD_NNN.yaml (if gap found)
           posts: Discord (max 1 proposal/week)

Hourly     AGENT-DEPLOYER [Hermes skill btc-agent-deployer]
           polls: proposals/approved/
           if new approval: spawns Builder → Builder writes collectors/{id}.py
```

---

## 4. Known Gaps and Broken Dependencies

### ⚠️ Gap 1: alt_watchlist.py — broken input key

**File:** `collectors/alt_watchlist.py`  
**Problem:** Reads `state/watchlist.json` for `.get('alts', [])` but `state/watchlist.json` contains keys `{last_updated, scan_timestamp, btc_dominance_trend, candidates, ...}` — no `alts` key. Collector always produces empty `{}` output.  
**Impact:** `data/alts/watchlist_prices.json` always has `"data": {}`. No agent reads this file anyway, so impact is zero currently — but if an agent is ever built to use alt rotation signals, this feeder is silent.  
**Fix:** Either rename the key in `state/watchlist.json` to include an `alts: []` list of symbols, or rewrite `alt_watchlist.py` to read `candidates` from the scan output.

---

### ⚠️ Gap 2: `data/alts/watchlist_prices.json` — orphan output

**File:** `data/alts/watchlist_prices.json`  
**Written by:** `alt_watchlist.py` (daily)  
**Read by:** No agent  
**Impact:** Alt price data is collected but never consumed. This also contributes to the `alt_watchlist.py` input bug above being invisible.

---

### ⚠️ Gap 3: `data/options/btc_options.json` — partially covered

**Status:** The `onchain-macro-analyst` briefing was updated this session to read this file and populate `options_pcr` and `options_max_pain_weekly`. However, this is a secondary consumer; options data deserves a dedicated analyst. A proposal (`prop_20260524_001`) to create an `options-analyst` agent is currently in **both** `proposals/pending/` and `proposals/approved/` — the approved copy exists but no agent has been built yet (Builder hasn't been triggered via `!deploy`).  
**Fix:** Run `!deploy prop_20260524_001` in Discord or WebUI to trigger Builder.

---

### ⚠️ Gap 4: `collection_monitor.py` stale threshold mismatch for `onchain`

**Problem:** `onchain.py` runs daily (once at 00:10 UTC) but `collection_monitor.py` has its stale threshold set to 4000s (~67 min). This means `data/onchain/mempool.json` and `data/onchain/blockchair.json` will show **RED for ~23 hours per day**.  
**Fix options:**  
  a. Increase stale threshold for `onchain` to 90000s (matching fear_greed).  
  b. Change `btc-onchain.timer` to run more frequently (e.g., every 2h).  
  Mempool fees change throughout the day; option (b) is better for data quality.

---

### ⚠️ Gap 5: `data/exchange_netflow/` and `data/social/` — legacy empty directories

Both directories are empty. `data/exchange_netflow/` was a placeholder before `netflow_collector.py` was written (which writes to `data/onchain/netflow.json`). `data/social/` has no collector and no agent reads it.  
**Fix:** Remove both directories to avoid confusion: `rmdir data/exchange_netflow data/social`

---

### ⚠️ Gap 6: `data/macro/btc_market.json` — stale at 00:10 UTC only

**Problem:** `macro.py` runs daily at 00:10 UTC (once). `btc_market.json` contains price, market cap, 24h change. The onchain-macro-analyst reads `btc_24h_change_pct` from it when it runs at 00:30 UTC (only 20 min later — fine). But it's 11+ hours stale when the reporter runs at 09:00 UTC.  
**Impact:** Reporter reads `state/portfolio.json` for price (via ws_prices), not `btc_market.json` directly. Risk is low but the CoinGecko call is free — could run more frequently.

---

### ⚠️ Gap 7: `data/onchain/blockchair.json` — no longer referenced in analyst briefing

The updated `onchain-macro-analyst/briefing.md` no longer lists `data/onchain/blockchair.json` as an input (it was in the old version). The file is still collected daily but no agent reads it.  
**Fix:** Either add it back to the analyst briefing (Blockchair has useful network stats like tx count, difficulty) or stop collecting it.

---

### ⚠️ Gap 8: Reporter reads `state/signals.json` — currently empty

`state/signals.json` contains `"active_signals": []` with a note that all strategies are watcher-compatible. The reporter reads it; this is fine but the reporter should handle the empty case gracefully (no crash risk, just no signal data in the report).

---

### ⚠️ Gap 9: `portfolio.demo_mode` vs `BYBIT_ACCOUNT_TYPE` mismatch

**State:** `portfolio.json` has `demo_mode: false` (not explicitly set) but `.env` has `BYBIT_ACCOUNT_TYPE=demo`. The reporter reads `portfolio.demo_mode` and will display "Mode: LIVE" incorrectly.  
**Fix:** Set `portfolio.demo_mode = true` explicitly in `portfolio.json`, OR update `reporter/briefing.md` to read mode from `.env` via `BYBIT_ACCOUNT_TYPE`.

---

### ✅ No Missing Input Files

All data files referenced in agent briefings exist on disk:
- `data/indicators/btc_{1h,4h,1d}.json` ✓
- `data/market/{funding_history,open_interest,long_short_ratio}.json` ✓
- `data/macro/{fear_greed_7d,btc_market}.json` ✓
- `data/macro/etf/flows.json` ✓
- `data/onchain/{mempool,netflow}.json` ✓
- `data/whales/large_transactions.json` ✓
- `data/options/btc_options.json` ✓
- `data/news/{articles,classified,flagged}.json` ✓
- `state/{portfolio,strategies,lessons,research,orchestrator-directive}.json` ✓
- `signals/live_triggers.json` ✓

---

## 5. Data Coverage Map

| Data file | Collector | Agent reader(s) | Gap? |
|-----------|-----------|-----------------|------|
| data/market/btc_candles_{1m,1h,4h,1d}.json | btc_candles.py | ta_engine.py (→ indicators) | None |
| data/market/ws_prices.json | ws_price_service.py | position_guardian.py, trader-entry | None |
| data/market/funding_history.json | bybit_derivatives.py | derivatives-analyst | None |
| data/market/open_interest.json | bybit_derivatives.py | derivatives-analyst | None |
| data/market/long_short_ratio.json | bybit_derivatives.py | derivatives-analyst | None |
| data/indicators/btc_{1h,4h,1d}.json | ta_engine.py | technical-analyst, signal_watcher.py | None |
| data/macro/fear_greed_7d.json | fear_greed.py | onchain-macro-analyst, sentiment-news-analyst | None |
| data/macro/btc_market.json | macro.py | onchain-macro-analyst | None |
| data/macro/etf/flows.json | etf_flow_collector.py | sentiment-news-analyst | None |
| data/onchain/mempool.json | onchain.py | onchain-macro-analyst | None (stale threshold bug) |
| data/onchain/blockchair.json | onchain.py | **None after briefing update** | ⚠️ Orphan |
| data/onchain/netflow.json | netflow_collector.py | onchain-macro-analyst | None |
| data/options/btc_options.json | options_collector.py | onchain-macro-analyst, [options-analyst pending] | Partial |
| data/whales/large_transactions.json | whale_collector.py | onchain-macro-analyst | None |
| data/news/articles.json | news_collector.py | news_classifier.py | None |
| data/news/flagged.json | news_collector.py | sentiment-news-analyst | None |
| data/news/classified.json | news_classifier.py | sentiment-news-analyst | None |
| data/alts/watchlist_prices.json | alt_watchlist.py | **None** | ⚠️ Orphan |
| data/historical/*.json | (seeded at init) | trader-management | None |
| data/analyst_reports/*.json | 4 analyst agents | hypothesis-generator, bull/bear researchers, synthesis | None |
| data/proposed_hypotheses.json | hypothesis-generator | bull-researcher, bear-researcher | None |
| data/bull_round{1,2}.json | bull-researcher | bear-researcher (r2), synthesis | None |
| data/bear_round{1,2}.json | bear-researcher | bull-researcher (r2), synthesis | None |
| data/debates/*.json | synthesis | (reference only, no active reader) | Acceptable |
| data/meta/collection_status.json | collection_monitor.py | chief (health monitoring), dashboard | None |
| state/research.json | synthesis | orchestrator, strategy-tester, reporter, risk-manager | None |
| state/strategies.json | strategy-tester | signal_watcher.py, trader-entry, trader-management, reporter, risk-manager | None |
| state/orchestrator-directive.json | orchestrator | signal_watcher.py, chief, risk-manager | None |
| state/portfolio.json | trader-entry | position_guardian, trader-management, risk-manager, reporter, orchestrator | None |
| signals/live_triggers.json | signal_watcher.py | btc-trigger-queue skill | None |
| signals/trigger_queue.json | btc-trigger-queue skill | risk-manager, trader-entry | None |
| data/exchange_netflow/ | **Nobody** | **Nobody** | ⚠️ Empty legacy dir |
| data/social/ | **Nobody** | **Nobody** | ⚠️ Empty legacy dir |

---

## 6. Proposed Improvements

### P1 — Immediate (bugs)

1. **Fix `alt_watchlist.py` input key**: Change `.get('alts', [])` to read the correct symbol list. The watchlist currently has `candidates: []` — either use that as the dynamic list or maintain a separate static symbol list in a new `state/symbol_watchlist.json`.

2. **Fix `collection_monitor.py` stale threshold for `onchain`**: Change threshold from 4000s to 90000s, OR change `btc-onchain.timer` to run every 2h (better). The current setup guarantees a permanent RED health indicator.

3. **Fix `portfolio.demo_mode` in portfolio.json**: Set to `true` explicitly so the reporter shows "DEMO" not "LIVE" while `BYBIT_ACCOUNT_TYPE=demo` is set.

4. **Deploy options-analyst**: `prop_20260524_001` is already in `proposals/approved/`. Run `!deploy prop_20260524_001` to trigger Builder. The options market (PCR 1.13, max pain $76K) is a high-signal blind spot that was confirmed in today's debates.

### P2 — Soon (gaps)

5. **Remove empty legacy directories**: `rmdir data/exchange_netflow data/social` to prevent confusion in future audits.

6. **Add `data/onchain/blockchair.json` back to onchain-macro-analyst briefing**, or stop collecting it. Blockchair has valuable data: tx count, block size, hash rate. Either use it or delete the collector code for it.

7. **Add a `data/alts/` consumer**: Either build an `alt-rotation-analyst` or fold the watchlist_prices.json reading into the orchestrator. Currently the alt scan results (`state/watchlist.json`) are written by what appears to be an inline orchestrator function — this should be a separate collector or formalized.

### P3 — Future improvements

8. **`btc-onchain.timer` frequency**: Run mempool.py every 2h (not once daily) — mempool fee pressure is intraday and affects execution decisions.

9. **`data/news/classified.json` coverage**: The classifier runs hourly at :30 but only classifies articles from the last 24h. Consider adding a `sentiment_score_aggregate` field (rolling average of daily bullish vs bearish article ratios) that the sentiment-news-analyst can trend over time.

10. **`data/historical/*.json` refresh**: These files were seeded at init. As new historical data accumulates, the backtester results drift. Consider a weekly re-fetch of historical data (btc_4h_6mo, btc_1d_2yr) to keep the backtester calibrated.

11. **`state/weekly-review.json` audit trail**: Currently only orchestrator writes this on Sundays. It would be valuable for the journal-agent to also append to a rolling weekly-reviews archive so multi-week P&L trends can be tracked.

---

## Appendix: Hermes Cron Schedule (UTC)

```
*/5  *  *  *  *   btc-trigger-queue-check (trigger processing)
 0   *  *  *  *   btc-agent-deployer-hourly
30   0  *  *  *   btc-morning-pipeline (analysts → debate → synthesis)
30   2  *  *  *   btc-strategy-tester-daily
 0   3  *  *  *   btc-trader-management-daily
 0   9  *  *  *   btc-reporter-daily
30  15  *  *  *   btc-orchestrator-daily
 0  10  *  *  0   btc-journal-weekly (Sundays)
 0  11  *  *  0   btc-chief-evaluator-weekly (Sundays)
```

## Appendix: systemd Timer Schedule (UTC)

```
Every  5 min   btc-candles       (Bybit kline → indicators)
Every 15 min   btc-news          (news_collector.py)
Every 30 min   btc-whale         (whale_collector.py)
Every  1 hr    btc-derivatives   (bybit_derivatives.py)
Every  1 hr    btc-options       (options_collector.py)
Every  1 hr    btc-news-classify (:30 offset, news_classifier.py)
Every  2 hr    btc-netflow       (:10 offset, netflow_collector.py)
Daily 00:10    btc-fear-greed, btc-macro, btc-onchain, btc-alt-watchlist
Daily 09:05    btc-etf-flow (+ 15:05, 21:05 UTC)
Daily 14:01    daily_reset       (via btc-daily-reset.service)
```

---

*Audit generated: 2026-05-24. All findings derived from reading actual files — no assumptions made about intended vs actual behavior.*

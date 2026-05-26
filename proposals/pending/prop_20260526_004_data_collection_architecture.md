# Data Collection Subsystem Architecture Review
**Proposal ID:** prop_20260526_004  
**Date:** 2026-05-26  
**Author:** Chief of Staff  
**Status:** pending  
**Type:** architecture_review  
**Scope:** Five areas — news source, resilience, monitoring/alerting, ownership, script fragility

---

## Current State (confirmed from live files)

### Collection fleet
12 collectors run as systemd `oneshot` services fired by `btc-*.timer` units under
`/etc/systemd/system/`. All source scripts live in `~/btc-agents/collectors/`. All write
JSON envelopes (`{"schema_version","collector","collected_at","stale_after_seconds","data"}`)
via `atomic_write()` to `data/`.

`btc-collection-monitor.service` runs `collectors/collection_monitor.py` as a persistent
daemon. Every 5 minutes it checks each output file and writes
`data/meta/collection_status.json` with three health fields per collector:
`file_health` (mtime), `content_health` (fingerprint staleness + data_count=0 check),
`content_unchanged_seconds`.

`~/.hermes/scripts/collection_alert.py` runs as a Hermes no_agent cron (`*/15 * * * *`)
and fires a Discord message when any collector is degraded. Silent on clean runs.

### Source / fallback inventory (audited 2026-05-26)

| Collector | Primary source | Fallback | No try/except |
|---|---|---|---|
| btc_candles | Bybit v5/market/kline | none | yes — bare crash |
| bybit_derivatives | Bybit v5/market/funding+OI+ratio | none | yes — bare crash |
| fear_greed | alternative.me/fng | none | yes — bare crash |
| macro | CoinGecko simple/price | none | minimal |
| netflow | CoinMetrics community v4 | none (writes "unavailable" record) | partial |
| onchain | Blockchair/bitcoin/stats + mempool.space/fees | none between them | partial |
| news | cryptocurrency.cv API (**402 — paywalled**) | CoinDesk RSS (stale, see §A) | yes |
| news_classify | reads articles.json | n/a (downstream) | — |
| options | Deribit API | Bybit options API | yes — multi try/except |
| whale | mempool.space blocks+txs | Blockchair transactions | yes — multi try/except |
| etf_flows | sosovalue.com API | farside.co.uk scrape | yes — multi try/except |
| alt_watchlist | Bybit spot tickers | error-handled but single source | partial |

### Agent data consumption
Agents are pure consumers — they read from `data/` and never write back to it.
The sentiment-news-analyst briefing does have a staleness guard:
`if classified.json collected_at > 4h old: set signal="data_stale"`. No other analyst
has an equivalent guard.

---

## Area A — News Source

### Problem

**Primary source dead.** `cryptocurrency.cv/api/v1/news` returns HTTP 402 on every run.
The collector falls through to CoinDesk RSS.

**Fallback is stale.** CoinDesk RSS articles currently dated May 22–23 (3–4 days old as
of proposal date). The 48h sliding window in `news_collector.py` drops articles as they
age, so `data_count` will eventually reach 0 and trip a red alert — but for now the file
has 15 articles that look plausible while carrying stale dates.

**Parse bug masks age.** `parse_dt()` truncates timestamps to 30 characters before
matching. CoinDesk RFC 2822 timestamps (`'Sat, 23 May 2026 20:52:21 +0000'`) are
exactly 31 chars — the truncation drops the last `0`, turning `+0000` into `+000`. Python
`strptime %z` requires exactly 4 digits, so all CoinDesk dates silently return `None`.
This means: (a) the 48h cutoff never fires on CoinDesk articles (they're immortal), and
(b) agents sort/filter news by date with everything returning `None`. The bug is in
`parse_dt()` at line 78 of `news_collector.py`. Fix is a one-line change (parse without
truncation, or use `email.utils.parsedate_to_datetime`).

**Monitor is semantically blind.** `content_unchanged_seconds` measures whether the file's
`data[]` fingerprint changes — not whether the newest article date is recent. Because
articles expire and get dropped from the 48h window, the file content changes on almost
every run even when no new articles arrive. Result: `content_health` stays green
indefinitely while serving 3-day-old news.

### Options

**Option A1 — Multi-feed RSS pool (recommended by operator, recommended here)**

Replace the single primary + single fallback with a pool of 4–6 free RSS feeds fetched
in parallel. Candidates with known BTC-relevant content:
- `https://cointelegraph.com/rss/tag/bitcoin`
- `https://decrypt.co/feed`
- `https://bitcoinmagazine.com/feed`
- `https://news.google.com/rss/search?q=bitcoin&hl=en-US&gl=US&ceid=US:en`
- `https://www.coindesk.com/arc/outboundfeeds/rss/` (keep as one of N, not sole fallback)
- `https://www.theblock.co/rss.xml`

Each RSS feed is polled independently. Articles are deduplicated by URL. If any feed
succeeds the run counts as successful. `source_count` is logged. A feed that 402s or
times out is skipped silently — the others carry the run.

Tradeoffs:
+ No API keys, no paywalls, can't 402 as a fleet (individual feeds may die but others
  carry on)
+ Operator is already building this
+ Google News RSS is self-healing (aggregates from dozens of publishers)
- RSS feeds have variable update frequency (minutes to hours)
- Quality varies; needs keyword filtering already in place
- Some feeds require User-Agent headers to avoid 403

**Option A2 — CryptoPanic free tier as aggregator**

`https://cryptopanic.com/api/v1/posts/?auth_token=<free>&filter=bitcoin` — free tier
requires an account and API token (obtainable without payment). Returns aggregated
BTC news from dozens of sources with sentiment labels.

Tradeoffs:
+ Aggregates many sources; single endpoint
+ Sentiment data bundled (reduces reliance on news_classifier.py)
- Requires an API token (another credential to manage/rotate)
- Free tier is rate-limited (adds a potential failure mode of its own)
- Token revocation would kill the whole feed

**Option A3 — Self-host cryptocurrency.cv open source**

The operator mentioned this option. The original source is open-source; running it locally
eliminates the 402 problem.

Tradeoffs:
+ Solves the 402 permanently
- Requires a running web service on the same host (additional process to maintain)
- Database/dependency setup not trivial
- Overkill given the free RSS pool is sufficient and the operator is already building it

### Recommendation: A1 with bug fix

Implement the RSS pool. Also fix `parse_dt()` — the 30-char truncation bug must be
patched regardless of which source is chosen; without it no CoinDesk-format date will
ever parse. Add a semantic freshness check to the monitor (see §C).

### Implementation steps
1. Patch `parse_dt()`: remove `[:30]` truncation or replace with
   `email.utils.parsedate_to_datetime()` for RFC 2822 strings.
2. Replace `fetch_cryptocv()` + single `fetch_coindesk_rss()` with a
   `fetch_rss_pool(feeds: list[str]) -> list[articles]` function that iterates the
   feed list, accumulates unique articles, and returns on first non-empty result or
   after trying all feeds.
3. Log `sources_tried`, `sources_succeeded`, and `new_count` per run.
4. Update `stale_after` in the envelope from 3600 to 900 (15 min) to match the timer
   cadence — the current 1h stale threshold is a leftover from when the source was
   fast and reliable.
5. Add semantic staleness check to monitor (see §C).

---

## Area B — Resilience: Single Points of Failure

### Problem

Five collectors have zero fallback and bare-crash failure modes:

**btc_candles** and **bybit_derivatives**: Both are Bybit-only with no try/except. If
Bybit's public API becomes temporarily unreachable (maintenance, rate limit, network
blip), these scripts exit with an unhandled exception. systemd marks the service as
failed; the timer will retry on schedule (~5 min for candles, ~60 min for derivatives),
but agents reading those files in between get stale data with no indication.

These are the most critical collectors — candles feed the TA engine which feeds
signal_watcher. A 30-minute gap in candle data could suppress a valid entry signal.

**fear_greed**: `fear_greed.py` is 12 lines with no try/except at all — an unhandled
exception crashes the process with no output file update. alternative.me is a free
community API with no SLA.

**macro** (CoinGecko): Minimal try/except, prints the error but still exits without a
useful output. CoinGecko free tier enforces strict rate limits (~30 req/min) and is
known to return 429s under load.

**netflow** (CoinMetrics community): Has error handling but degrades to writing an
`"unavailable"` record. The onchain-macro analyst reads this as signal=unknown. Not a
crash, but silently produces a content-free output file.

### Options

**Option B1 — Add secondary source fallbacks to critical collectors (recommended)**

Priority order:
1. `btc_candles` / `bybit_derivatives`: Add Binance public API as fallback
   (`api.binance.com/api/v3/klines` for candles, `fapi.binance.com` for perpetual
   funding/OI). Both are public, no key required. Logic: try Bybit, catch exception,
   try Binance, wrap in try/except.
2. `fear_greed`: Add CoinStats free endpoint
   (`api.coinstats.app/public/v1/coins/bitcoin`) as a fear/greed proxy, or use the
   CNN Fear & Greed screenscrape as fallback. Wrap all attempts in try/except.
3. `macro`: Add CoinStats or CryptoCompare free tier as fallback for BTC price/market cap.
4. `netflow`: CoinGlass community API (`open-api.coinglass.com/public/v2`) has a free
   exchange flow endpoint as fallback.

Tradeoffs:
+ Each collector gains one independent fallback
+ Degraded output clearly labelled with `source=fallback`
+ No new credentials needed for Binance public endpoints
- Code complexity grows per collector
- Fallback testing requires simulating primary failures (non-trivial)

**Option B2 — Shared fallback registry + supervisor**

Create a `_fallback.py` utility that holds a registry of fallback URLs per data type.
Collectors call `try_sources(primary, fallbacks)`. A supervisor (systemd or Hermes cron)
detects consecutive failures and escalates.

Tradeoffs:
+ DRY — fallback logic in one place
+ Supervisor can try immediate retry before waiting for next timer tick
- More infrastructure to build and maintain
- Overkill for the current fleet size

**Option B3 — Wrap all collectors in defensive shell script with alerting only**

Don't add fallbacks. Instead, wrap each `ExecStart` in a shell script that captures exit
code and posts to a failure log if non-zero. Rely on the monitor + alert cron to surface
failures.

Tradeoffs:
+ Minimal code change
- Doesn't actually improve data availability
- The monitor's 15-min check window means up to 15 min of silent failure per event

### Recommendation: B1 staged

Address the two highest-impact SPOFs first: `btc_candles` (feeds TA engine and
signal_watcher directly) and `bybit_derivatives` (feeds derivatives analyst). Add
try/except wrappers and Binance fallback. Then `fear_greed` and `macro` in a second pass
(lower frequency, analysts tolerate stale better). `netflow` already degrades gracefully.

Do not implement B2 yet — premature for this fleet size. Revisit if the fleet grows
beyond ~20 collectors.

### Implementation steps
1. **btc_candles**: Wrap `fetch()` in try/except. On exception, try
   `api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=200`. Normalize
   Binance candle format to match Bybit output schema. Log `source=bybit|binance`.
2. **bybit_derivatives**: Same pattern. Fallback sources:
   - Funding: `fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=50`
   - OI: `fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT`
   - Long/short: `fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=24`
3. **fear_greed**: Wrap entire script in try/except. On failure write a stub record
   (`value: null, source: "unavailable"`) rather than crashing. Timer retry interval
   is already 24h — a crash leaves no data until the next day.
4. **macro**: Same defensive wrap.
5. Each change is a standalone PR / no new proposals required — these are collector
   patches, not new agents.

---

## Area C — Monitoring and Alerting

### Problem

Two gaps remain after the content-fingerprint upgrade and alert cron deployment:

**Gap 1 — Semantic staleness for news.** The fingerprint approach measures "did the
data array change" — not "is the newest article recent." Because news_collector.py
constantly drops and accumulates articles via the 48h window, the fingerprint changes
on almost every write even when no new article arrives. `content_unchanged_seconds`
stays near 0 indefinitely. A collector serving 4-day-old news reads as perfectly healthy.

**Gap 2 — No per-collector staleness context in alerts.** When collection_alert.py
fires, the Discord message identifies the degraded collector and its health code but
doesn't say "newest article is 3 days old" or "last successful netflow fetch was 14h ago."
The operator gets "news: DEGRADED-BUT-WRITING" but has to manually inspect the file to
understand severity.

**Not a gap (working correctly):** The `data_count=0` check does immediately catch a
collector that writes empty envelopes (the original news failure mode after the fix).
Threshold for `content_unchanged_seconds` degradation warnings is generous (12x
file_stale threshold) which is correct for avoiding false positives on genuinely quiet
market periods.

### Options

**Option C1 — Add semantic checks per collector type (recommended)**

Extend `collection_monitor.py` to inspect the `published_at` / `date` / `time` fields
of the newest record for collectors where recency matters. Add a `newest_record_age_seconds`
field to the status entry.

Collectors needing semantic date checks:
- `news`: check newest `published_at` in `data[]` — alert if > 6h old
- `news_classified`: same
- `netflow`: check `date` field — alert if > 36h old (daily collector, some lag normal)
- `etf_flows`: check date in data — alert if > 48h old (trading day lag expected)
- `fear_greed`: check `timestamp` in first record — alert if > 36h old

Collection_alert.py then reads `newest_record_age_seconds` and adds it to the message:
"news: CONTENT STALE — newest article 72h old"

Tradeoffs:
+ Catches the exact failure mode that slipped through on May 24
+ One addition to the monitor loop, no new services
- Field names vary per collector (requires per-collector config)
- Needs a mapping of collector → record date field

**Option C2 — Agent-side staleness guards (defensive reads)**

Instead of enhancing the monitor, add staleness checks in each analyst briefing:
"if newest article in classified.json is >6h old, set signal=data_stale."
The sentiment analyst already has this for `collected_at` — extend to `published_at`
and extend the pattern to all analysts.

Tradeoffs:
+ Each analyst is self-defending
+ No infrastructure change
- Doesn't alert the operator proactively — only discovered when the analyst outputs
  `data_stale`, which is only visible in the morning pipeline output
- Requires patching 5+ briefing.md files

**Option C3 — Alert thresholds tuning only**

Reduce `CONTENT_STALE_WARN['news']` in collection_alert.py from `1800 * 6 = 10800s`
(3h) to `3600s` (1h). The content fingerprint does change (articles drop out) but changes
less frequently than one might expect — a 1h threshold would catch a degraded-but-writing
state within one 15-min alert cycle.

Tradeoffs:
+ One-line change, deployed immediately
- Doesn't add semantic date context to alerts
- Fingerprint churn from article expiry could still mask the real issue for hours

### Recommendation: C1 + C3 as safety net

C3 is trivial to deploy now (update collection_alert.py thresholds). C1 is the complete
fix — add `newest_record_age_seconds` to the monitor and surface it in alerts. Do C1 as
a follow-on proposal once the news RSS pool (§A) is deployed and the monitor patch
cadence is established.

Do C2 (agent-side guards) in parallel — it's defense-in-depth, not a replacement for C1.
The sentiment analyst already has it half-done; extend the pattern.

### Implementation steps
1. (Immediate, no proposal needed) Patch `collection_alert.py`: reduce
   `CONTENT_STALE_WARN['news']` from 10800 to 3600. Copy updated file to
   `~/.hermes/scripts/collection_alert.py` (the copy issue — see §E).
2. (Follow-on proposal) Patch `collection_monitor.py`: add a `SEMANTIC_DATE_FIELDS`
   config dict mapping collector name to the dotted path of the newest record's date
   field. In the monitor loop, after the fingerprint check, attempt to parse the
   newest record's date and write `newest_record_age_seconds`. Backward compatible.
3. (Follow-on proposal) Patch `collection_alert.py`: if `newest_record_age_seconds`
   is present and exceeds threshold, include "newest record: Xh old" in the alert line.
4. (Now, no proposal) Patch sentiment-news-analyst briefing to check `published_at`
   of newest article, not just `collected_at` of the file. Other analysts: add a
   "data stale" guard where they currently trust the file unconditionally.

---

## Area D — Ownership: systemd vs Hermes

### Problem

**Current split:**
- **systemd timers** (11): all data collectors. Fire on their own clock. Hermes does not
  schedule, monitor, restart, or log them. Failure is invisible unless the monitor catches
  it and the alert cron fires.
- **Hermes no_agent crons** (6): alt-watchlist-daily, intraday-risk-watchdog, chief-triage-daily,
  btc-trigger-queue-check, collection-alert, btc-agent-deployer-hourly. These run scripts
  that Hermes does schedule, restart on failure, and log.

**Alt-watchlist inconsistency:** The systemd `btc-alt-watchlist.timer` is now **disabled**
(operator ran `systemctl disable` today). The Hermes cron `btc-alt-watchlist-daily` handles
it. The systemd unit file still exists at `/etc/systemd/system/btc-alt-watchlist.{service,
timer}`. A future `daemon-reload` or reboot could re-enable it inadvertently if someone
runs `systemctl enable btc-alt-watchlist.timer` by mistake.

**The `--replace` gateway restart bug (fixed today)** exposed a deeper governance gap: for
~90 restarts/day, every once-daily Hermes LLM cron silently did not complete. The systemd
collectors were completely unaffected because they don't depend on the Hermes gateway being
stable. This is a feature of the current split, not a bug.

### Options

**Option D1 — Keep the split, harden the boundary (recommended)**

The systemd-for-collection, Hermes-for-agents split is architecturally sound. Collectors
should be independent of Hermes gateway health — the gateway restart bug proved this.

Hardening steps:
- Remove (not just disable) the `btc-alt-watchlist.timer` and `btc-alt-watchlist.service`
  unit files. Hermes cron owns alt-watchlist entirely.
- For the remaining systemd collectors: add `OnFailure=` directives pointing to a
  lightweight notifier service that appends to `data/meta/collector_failures.json`.
  collection_monitor can then surface this in the status file.
- Add `Restart=on-failure` and `RestartSec=60` to high-frequency collectors (btc-candles,
  btc-derivatives, btc-news) so a transient failure self-heals within 1 minute rather than
  waiting for the next timer tick.

Tradeoffs:
+ Collectors survive Hermes gateway instability (proven value today)
+ Clean governance boundary: OS owns data, Hermes owns decisions
+ Minimal change
- Failures in systemd collectors still can't be auto-remediated by Hermes
- The operator must use `journalctl` to debug systemd collector failures (not visible in
  Hermes logs)

**Option D2 — Migrate collectors to Hermes no_agent crons**

Replace systemd timers with `hermes cron create --no-agent --script` entries. Hermes
would then schedule, log, and restart all collectors.

Tradeoffs:
+ All scheduling in one place
+ Hermes logs visible in gateway log
- Collectors become dependent on Hermes gateway stability (the restart bug would have
  also killed data collection — makes the system more fragile, not less)
- Hermes cron `--no-agent` scripts must live in `~/.hermes/scripts/` — exacerbates
  the script fragility problem (see §E) for every collector
- No clear advantage over systemd for fire-and-forget oneshot scripts

**Option D3 — Hybrid: keep systemd timers, add Hermes-aware failure notification**

Keep systemd timers but add a collector-failure sidecar: a new no_agent Hermes cron
(e.g., every 10 min) that reads `journalctl` output for `btc-*.service` units and posts
failures to Discord. More granular than the monitor's mtime/fingerprint checks.

Tradeoffs:
+ Best of both worlds in theory
- Requires root/sudo access to read `journalctl` from btc-agent user (may work with
  `journalctl --user` or via polkit rule)
- Duplicates some of what collection_monitor already does
- Adds another cron job for marginal gain

### Recommendation: D1

Keep the split. Remove the alt-watchlist unit files (don't leave disabled units on disk).
Add `Restart=on-failure` to the 3 high-frequency collectors. Add `OnFailure=` notifier
for systemd-level crash visibility. No new agent required.

### Implementation steps
1. `sudo rm /etc/systemd/system/btc-alt-watchlist.{service,timer}` and
   `sudo systemctl daemon-reload`. Hermes cron owns this entirely from now on.
2. For each of `btc-candles.service`, `btc-news.service`, `btc-derivatives.service`:
   add to `[Service]` block:
   ```
   Restart=on-failure
   RestartSec=60
   ```
3. Create `/etc/systemd/system/btc-collector-notify@.service`:
   ```ini
   [Unit]
   Description=Collector failure notifier for %i
   [Service]
   Type=oneshot
   User=btc-agent
   ExecStart=/bin/bash -c 'echo "{\"collector\":\"%i\",\"failed_at\":\"$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)\"}" >> /home/btc-agent/btc-agents/data/meta/collector_failures.json'
   ```
   Then add `OnFailure=btc-collector-notify@%i.service` to each `btc-*.service` unit.
4. The collection_monitor or alert script can then surface entries from
   `collector_failures.json` in Discord messages.

---

## Area E — Script Fragility (Drift Problem)

### Problem

The operator's fix for broken no_agent cron scripts was to **copy** the source files from
`~/btc-agents/` into `~/.hermes/scripts/`. This works but creates a fragility: the copy
is not linked to the source. Any future edit to the source file is silently not reflected
in the running cron until a manual re-copy is done.

**Current copies and their sources:**

| File in ~/.hermes/scripts/ | Source in ~/btc-agents/ | Last synced |
|---|---|---|
| `agent_deployer.py` | `services/agent_deployer.py` | May 24 15:31 |
| `collection_alert.py` | `services/collection_alert.py` | May 26 02:12 |
| `collectors/alt_watchlist.py` | `collectors/alt_watchlist.py` | May 26 00:46 |
| `collectors/_utils.py` | `collectors/_utils.py` | May 26 00:47 |
| `orchestrator.py` | `services/orchestrator.py` | May 24 21:51 |
| `services/chief_triage.py` | `services/chief_triage.py` | May 26 00:46 |
| `services/intraday_risk_watchdog.py` | `services/intraday_risk_watchdog.py` | May 25 13:35 |
| `trigger_queue_processor.py` | `services/trigger_queue_processor.py` | May 24 15:23 |

8 copied files. Any of these could drift. The ones most likely to be edited:
`chief_triage.py` (the triage logic evolves as new failure modes are discovered),
`collection_alert.py` (thresholds will be tuned), `alt_watchlist.py` (if a new exchange
is added), `trigger_queue_processor.py` (as signal flow logic evolves).

### Options

**Option E1 — Symlinks (recommended)**

Replace copies with symbolic links:
```bash
ln -sf ~/btc-agents/services/chief_triage.py ~/.hermes/scripts/services/chief_triage.py
# etc.
```

Hermes resolves `script:` by reading the file at runtime — it does not cache the content.
A symlink works identically to a copy from Hermes's perspective. Edit the source once;
the cron picks it up on the next tick. No sync step required.

Tradeoffs:
+ Zero maintenance — source and Hermes always in sync
+ Trivial to implement (replace files with links)
- If `~/btc-agents/` is on a separate mount or the path changes, all links break silently
- Symlinks require the source path to be absolute and stable (it is — `/home/btc-agent/btc-agents/`)

**Option E2 — Upstream fix to Hermes (resolve script paths from workdir)**

The root cause is that Hermes resolves no_agent `script:` paths only from
`~/.hermes/scripts/`, ignoring the job's `workdir`. If it resolved from workdir first,
no copies would be needed — `script: services/chief_triage.py` would resolve to
`/home/btc-agent/btc-agents/services/chief_triage.py` when `workdir=/home/btc-agent/btc-agents`.

This is a Hermes framework bug. The operator mentioned NousResearch/hermes-agent #23272
(the `--replace` issue) — this would be a second issue to file.

Tradeoffs:
+ Permanent fix — no copies, no symlinks, no drift ever
+ Reduces cognitive overhead for future no_agent cron creation
- Requires an upstream PR and a Hermes release — not in our control
- Timeline unknown

**Option E3 — Automated sync script (cron-driven cp)**

Add a no_agent Hermes cron (or systemd timer) that runs `cp source dest` for each
tracked file on a schedule (e.g., every 6h). Log diffs to detect when sync was needed.

Tradeoffs:
+ Compatible with existing Hermes path resolution
+ Detects drift automatically
- Introduces a 6h drift window between source edit and cron pickup
- More moving parts; a failing sync cron goes unnoticed

### Recommendation: E1 (symlinks) immediately + E2 as upstream issue

E1 is a 10-minute fix. Replace all 8 copies with symlinks now. The only risk (broken
symlink if path changes) is extremely low on a stable server deployment.

File an upstream Hermes issue for E2 simultaneously. If/when it lands, remove the
symlinks — the crons will just work from workdir.

### Implementation steps
1. For each file in the table above, run:
   ```bash
   ln -sf /home/btc-agent/btc-agents/<source_path> /home/btc-agent/.hermes/scripts/<dest_path>
   ```
   Specifically:
   ```bash
   ln -sf ~/btc-agents/services/agent_deployer.py       ~/.hermes/scripts/agent_deployer.py
   ln -sf ~/btc-agents/services/collection_alert.py     ~/.hermes/scripts/collection_alert.py  
   ln -sf ~/btc-agents/collectors/alt_watchlist.py      ~/.hermes/scripts/collectors/alt_watchlist.py
   ln -sf ~/btc-agents/collectors/_utils.py             ~/.hermes/scripts/collectors/_utils.py
   ln -sf ~/btc-agents/services/orchestrator.py         ~/.hermes/scripts/orchestrator.py
   ln -sf ~/btc-agents/services/chief_triage.py         ~/.hermes/scripts/services/chief_triage.py
   ln -sf ~/btc-agents/services/intraday_risk_watchdog.py ~/.hermes/scripts/services/intraday_risk_watchdog.py
   ln -sf ~/btc-agents/services/trigger_queue_processor.py ~/.hermes/scripts/trigger_queue_processor.py
   ```
2. Verify each link resolves: `ls -la ~/.hermes/scripts/**/*.py ~/.hermes/scripts/*.py`
3. Run one manual tick of an affected cron to confirm it still works:
   `hermes cron run btc-chief-triage-daily`
4. File upstream issue: "no_agent cron script: should resolve relative paths from workdir
   before falling back to ~/.hermes/scripts/". Reference the operator's manual fix as
   motivation.

---

## Summary and Priority Order

| Priority | Area | Action | Effort | Risk |
|---|---|---|---|---|
| P0 — now | A (news parse bug) | Fix `parse_dt()` 30-char truncation | 1 line | none |
| P0 — now | E (script fragility) | Replace copies with symlinks | 10 min | low |
| P1 — this week | A (news source) | Operator-led RSS pool implementation | operator-owned | low |
| P1 — this week | C (alert threshold) | Reduce news CONTENT_STALE_WARN to 3600 | 1 line | none |
| P1 — this week | D (alt-watchlist) | Remove defunct systemd unit files | 2 commands | low |
| P2 — next sprint | B (SPOF collectors) | Binance fallback for btc_candles + derivatives | medium | medium |
| P2 — next sprint | C (semantic staleness) | Add newest_record_age to monitor | medium | low |
| P2 — next sprint | D (systemd hardening) | Add Restart + OnFailure to collector units | medium | low |
| P3 — backlog | B (other SPOFs) | fear_greed, macro defensive wraps | low | low |
| P3 — backlog | C (agent-side guards) | Stale-data guards in analyst briefings | low | none |
| upstream | E (root cause) | File Hermes issue for workdir script resolution | 30 min | none |

**Total new Hermes agents proposed: 0.** All recommendations are collector patches,
configuration changes, symlinks, and systemd unit changes. No new agent deployments are
required to implement this proposal.

---

## Approval instructions

To approve: move this file to `proposals/approved/` and implement the P0 items
(parse_dt fix and symlinks) manually — they require no Hermes deployer involvement.
P1 and P2 items should each become discrete implementation PRs / operational change
proposals against `proposals/PROPOSAL_SCHEMA.md` before execution.

To reject: move to `proposals/rejected/` with a note on which areas were declined.

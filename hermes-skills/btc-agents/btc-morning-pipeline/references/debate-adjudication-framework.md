# Debate Adjudication Framework

## Purpose
Synthesis agent must adjudicate bull vs. bear arguments across 2 rounds per hypothesis. This framework ensures consistent, evidence-backed verdicts.

## Adjudication Criteria (in priority order)

### 1. **Temporal Validity** (highest priority)
**Question:** Have entry conditions already expired or resolved?

- **Strong bear signal:** Entry window defined by a time-specific event (e.g., "extreme oversold at RSI 29.49") has already passed. If the bounce has already occurred between May 24→25 data, entering on May 25 is chasing momentum captured, not executing the thesis.
- **Rebuttal weakness:** Bull arguing regime change validates thesis is circular—regime change PROVES the bounce happened, not that it will sustain.
- **Example:** hch_20260524_001 (Mean Reversion Long) — May 24 RSI 29.49 was trigger; by May 25 RSI 65.95 with +1% bounce already occurred. Entry window expired. Bear wins.

### 2. **Evidence Strength** (analyst agreement)
**Question:** How many independent analysts support each side? Is evidence fresh and consistent?

- Count supporting signals per hypothesis across all 5 analyst reports.
- Weight fresh data (produced within 2 hours) higher than stale data.
- Conflicting analyst signals → mark as "inconclusive" unless one side has overwhelming consensus.
- Example: If technical says bullish but options show max pain below spot (bearish gravity), classify as inconclusive rather than forcing a winner.

### 3. **Logical Consistency** (Round 2 rebuttals)
**Question:** Does the Round 2 counter-argument address the opponent's specific claims or just repeat Round 1 arguments?

- **Strong counter:** Identifies temporal data staleness, contradictory analyst data, or structural invalidation.
- **Weak counter:** Restates original thesis without addressing opponent's critique.
- **Example:** Bull's Round 2 claiming "regime shift is confirmation" is weaker than "OI reversal from contraction to expansion is the whale accumulation signature—weak hands purged, institutions pyramiding" (addresses data contradiction head-on).

### 4. **Risk/Reward Alignment** (quantitative check)
**Question:** Does the hypothesis still maintain the promised edge given current market state?

- If entry conditions have degraded or shifted against the thesis, downgrade confidence even if the direction is correct.
- If entry window has narrowed (support level now close, resistance already tested), mark risk/reward as materially worse.
- Example: If entry was "bounce from 76,500 support" but price is already at 77,528, upside to 79,394 target is narrower and risk has increased.

---

## Verdict Assignment

### Bull Wins
- Entry conditions remain valid and time-sensitive triggers not yet triggered.
- Structural support (whales, sentiment, technical alignment) is fresh and converging.
- Bear's counter is speculative or makes unfounded assumptions.
- Risk/reward ratio intact.

### Bear Wins
- Entry window has expired or already partially resolved.
- Analyst data contradicts the thesis (e.g., OI contraction vs. expansion mismatch).
- Max pain gravity, funding rate weakness, or other structural headwinds have intensified.
- Bull's rebuttal is circular or ignores data contradictions.

### Inconclusive
- Evidence is genuinely split across analysts (e.g., technical bullish vs. options hedging bearish).
- Insufficient fresh data to adjudicate (stale analyst reports).
- Both sides make defensible points with no clear data victory.
- **Action:** Flag for Strategy Tester to run on both directions or require volume/duration confirmation before entering.

---

## Example Adjudication: hch_20260524_001

**Original Hypothesis:** Daily Mean Reversion Long from Extreme Oversold + Accumulation  
**Bull Round 1:** May 24 oversold (RSI 29.49) + whale accumulation (vtltvd 4.2) = capitulation bottom. Expect 2.5–3.5% bounce.  
**Bear Round 1:** Regime already shifted from "mean_reverting" to "bullish_accumulation." OI reversed from contraction to expansion. Entry window was May 24, not May 25.  
**Bull Round 2:** Regime shift PROVES the thesis worked. Bounce occurred exactly as predicted. Whale accumulation remains structural support.  
**Bear Round 2:** Bull's reframe is circular. Proving the bounce happened ≠ proving it will sustain. By May 25, market is in distribution phase, not accumulation phase. Entry into exhausted bounce faces headwind.

**Adjudication:**
1. **Temporal Validity:** Entry trigger (May 24 extreme oversold) has already passed. Bounce occurred 76,848→77,528 (+1%). May 25 entry is post-event. **BEAR wins.**
2. **Evidence Strength:** OI reversal (contraction→expansion) is factual, not opinion. Regime shift is analyst-validated across 5 reports. **BEAR supported.**
3. **Logical Consistency:** Bear's temporal critique is devastating. Bull's circular reframe ("regime change = thesis validated") doesn't address the expired entry window. **BEAR wins.**
4. **Risk/Reward:** May 25 entry faces distribution headwind, entry already 1% into bounce. Upside to 79,394 requires EMA200 breakout. **BEAR wins.**

**Verdict:** **BEAR WINS (0.82 confidence)** — Entry conditions expired; bounce already occurred.

---

## Synthesis Notes

- Verdicts with confidence <0.60 should be reviewed manually or marked inconclusive.
- If both sides have confidence >0.75, escalate to human review (suggests hypothesis is genuinely bifurcated and requires domain expertise).
- Always include concessions in the adjudication (e.g., "whale accumulation is real and structural" even though overall verdict favors bear).
- Write the winning argument summary in clear, evidence-backed language for Strategy Tester to understand why a hypothesis was approved/rejected.

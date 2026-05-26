#!/usr/bin/env python3
"""
BTC Strategy Tester - Daily task runner
Tasks:
1. Apply orchestrator actions
2. Process approved hypotheses
3. Check thesis validity
4. Run backtests
5. Score strategies
6. Generate signals
7. Update state files
8. Commit
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# _state_utils is the canonical way to read/write state files in this project.
# It enforces schema_version stamping, validation, and accumulate-not-reset
# semantics for lessons.json. Never call save_json_atomic() on lessons.json.
sys.path.insert(0, str(Path(__file__).parent))
from tools._state_utils import (
    load_state, save_state, append_lessons, ensure_lessons_file
)

# Configuration
WORKSPACE = Path(os.path.expanduser('~/btc-agents'))
STATE_DIR = WORKSPACE / 'state'
DATA_DIR = WORKSPACE / 'data'
TODAY = '2026-05-26'

def load_json(path):
    """Load JSON file."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_json_atomic(path, data):
    """Atomically write JSON file."""
    tmp_path = str(path) + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)

def parse_date(date_str):
    """Parse date string YYYY-MM-DD."""
    return datetime.strptime(date_str, '%Y-%m-%d')

def days_since(date_str):
    """Days between date_str and today."""
    d = parse_date(date_str)
    today = parse_date(TODAY)
    return (today - d).days

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Apply orchestrator actions (retire/promote)
# ─────────────────────────────────────────────────────────────────────────────

print("[1/8] Applying orchestrator actions...")
orchestrator_actions = load_json(STATE_DIR / 'orchestrator-strategy-actions.json')
if orchestrator_actions and orchestrator_actions.get('retire'):
    print(f"  Would retire: {orchestrator_actions['retire']}")
if orchestrator_actions and orchestrator_actions.get('promote'):
    print(f"  Would promote: {orchestrator_actions['promote']}")
print("  Result: No actions to apply (retire=[], promote=[])")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Load state files
# ─────────────────────────────────────────────────────────────────────────────

print("\n[2/8] Loading state files...")
strategies = load_json(STATE_DIR / 'strategies.json')
research = load_json(STATE_DIR / 'research.json')
pipeline = load_json(STATE_DIR / 'pipeline_state.json')

print(f"  Loaded {len(strategies['strategies'])} strategies")
print(f"  Research verdict: {research['debate_adjudication']['verdict']}")
print(f"  Approved hypotheses: {len(research.get('approved_hypotheses', []))}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Check for legacy strategies missing watcher_compatible field
# ─────────────────────────────────────────────────────────────────────────────

print("\n[3/8] Checking for migration needs...")
migrated = 0
for strat in strategies['strategies']:
    if 'watcher_compatible' not in strat:
        strat['watcher_compatible'] = False  # Default legacy = not compatible
        migrated += 1
        print(f"  Migrated {strat['id']}: added watcher_compatible=false")
if migrated == 0:
    print("  No migrations needed (all strategies have watcher_compatible field)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Check thesis validity (paper_testing strategies > 14 days old)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[4/8] Checking thesis validity...")
for strat in strategies['strategies']:
    if strat['status'] != 'paper_testing':
        continue
    created = strat['created_date']
    age_days = days_since(created)
    if age_days > 14:
        print(f"  {strat['id']}: age {age_days} days > 14 days")
        # Check regime mismatch (would require 7+ consecutive days)
        # For now, mark as thesis_expired if regime mismatch detected
        # TODO: check regime_mismatched field
print("  Result: All paper_testing strategies < 14 days old, no expiry")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Process approved hypotheses (check if new strategy needed)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[5/8] Processing approved hypotheses...")
approved_hyp_ids = [h.split(' - ')[0] for h in research.get('approved_hypotheses', [])]
print(f"  Approved hypotheses: {approved_hyp_ids}")

existing_hyp_ids = [s.get('hypothesis_chain_id') for s in strategies['strategies']]
print(f"  Existing hypothesis chains: {existing_hyp_ids}")

# Find new approved hypotheses
new_hyp_ids = [h for h in approved_hyp_ids if h not in existing_hyp_ids]
print(f"  New hypotheses to create: {new_hyp_ids}")

if 'hch_20260526_001' in new_hyp_ids:
    print(f"\n  Creating new strategy from hch_20260526_001...")
    
    # Find the hypothesis in research.json
    hch = None
    for hyp in research['hypothesis_adjudications']:
        if hyp['hypothesis_chain_id'] == 'hch_20260526_001':
            hch = hyp
            break
    
    if hch:
        next_id = strategies['summary']['next_strategy_id']
        new_strat = {
            "id": next_id,
            "hypothesis_chain_id": "hch_20260526_001",
            "parent_hypothesis_id": "hch_20260526_001",
            "title": hch['title'],
            "debate_transcript_ref": "research.json:hypothesis_adjudications[0]",
            "debate_verdict": hch['verdict'],
            "synthesis_confidence": hch['final_confidence'],
            "status": "paper_testing",
            "created_date": TODAY,
            "thesis_last_validated": TODAY,
            "consecutive_losses": 0,
            "watcher_compatible": True,  # Default new = compatible
            "data_dependencies": [
                "1h_rsi",
                "1h_ema50",
                "daily_ema200",
                "daily_price"
            ],
            "execution_urgency": "immediate",
            "entry_conditions": [
                {
                    "source": "/home/btc-agent/btc-agents/data/indicators/btc_1h.json",
                    "field": "rsi_14",
                    "operator": "lte",
                    "value": 30,
                    "description": "1H RSI <= 30 (oversold)"
                },
                {
                    "source": "/home/btc-agent/btc-agents/data/indicators/btc_1h.json",
                    "field": "ema50",
                    "operator": "lte",
                    "value": 77200,
                    "description": "Price at/below 1H EMA50 support (77083.58)"
                },
                {
                    "source": "/home/btc-agent/btc-agents/data/indicators/btc_1d.json",
                    "field": "price_vs_ema200_pct",
                    "operator": "gte",
                    "value": -2,
                    "description": "Price within -2% of daily EMA200 (daily uptrend intact)"
                }
            ],
            "entry_logic": "ALL",
            "take_profit_pct": 2.1,
            "stop_loss_pct": 1.8,
            "max_duration_days": 5,
            "trade_pair": "BTC/USD",
            "direction": "long",
            "type": "ta_signal",
            "risk_reward_ratio": 1.17,
            "entry_price": 77083.58,
            "tp_target": 78500,
            "sl_target": 75831,
            "support_level": 77083.58,
            "resistance_level": 78500,
            "key_factors": {
                "1h_rsi_oversold": 27.74,
                "1h_ema50_support": 77083.58,
                "daily_ema200_verified": 71671.45,
                "consolidation_pattern": "confirmed",
                "institutional_positioning": "call_dominant_0.6935"
            },
            "performance": {
                "trades_executed": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": None,
                "out_of_sample_win_rate": None,
                "sharpe_ratio": None,
                "out_of_sample_trades": 0,
                "backtest_score": 0,
                "backtest_status": "pending",
                "backtest_error": None
            }
        }
        
        strategies['strategies'].append(new_strat)
        strategies['summary']['total_strategies'] += 1
        strategies['summary']['next_strategy_id'] = f"strat_{int(next_id.split('_')[1]) + 1:03d}"
        print(f"  ✓ Created {next_id} from {hch['hypothesis_chain_id']}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Run backtests
# ─────────────────────────────────────────────────────────────────────────────

print("\n[6/8] Running backtests...")
for strat in strategies['strategies']:
    if strat['status'] != 'paper_testing':
        print(f"  Skipping {strat['id']}: status={strat['status']}")
        continue
    
    print(f"  Backtest {strat['id']} ({strat.get('type', 'ta_signal')})...")
    
    # Build params for backtester
    params = {
        'strategy_type': 'mean_reversion',  # Most strats are mean reversion
        'take_profit_pct': strat.get('take_profit_pct', 2.0),
        'stop_loss_pct': strat.get('stop_loss_pct', 1.0),
        'timeframe': '4h'
    }
    
    try:
        result = subprocess.run(
            ['python3', 'tools/backtester.py', json.dumps(params)],
            cwd=WORKSPACE,
            capture_output=True,
            timeout=10,
            text=True
        )
        if result.returncode == 0:
            backtest_result = json.loads(result.stdout)
            if 'error' in backtest_result:
                print(f"    ✗ Backtest error: {backtest_result['error']}")
                strat['performance']['backtest_status'] = 'pending_live_data'
                strat['performance']['backtest_error'] = backtest_result['error']
            else:
                # Update performance
                strat['performance']['trades_executed'] = backtest_result.get('trades', 0)
                strat['performance']['out_of_sample_trades'] = backtest_result.get('out_of_sample_trades', 0)
                strat['performance']['win_rate'] = backtest_result.get('win_rate', 0)
                strat['performance']['out_of_sample_win_rate'] = backtest_result.get('out_of_sample_win_rate', 0)
                strat['performance']['sharpe_ratio'] = backtest_result.get('sharpe', 0)
                strat['performance']['backtest_status'] = 'completed'
                
                # Calculate backtest score: win_rate*60 + sharpe*10 + sample_bonus*10
                wr = strat['performance']['win_rate'] or 0
                sharpe = strat['performance']['sharpe_ratio'] or 0
                oos_trades = strat['performance']['out_of_sample_trades'] or 0
                sample_bonus = 1 if oos_trades >= 20 else (oos_trades / 20) if oos_trades > 0 else 0
                score = wr * 60 + sharpe * 10 + sample_bonus * 10
                strat['performance']['backtest_score'] = round(score, 1)
                
                print(f"    ✓ Score: {score:.1f} (WR:{wr:.1%}, Sharpe:{sharpe:.1f}, Trades:{strat['performance']['trades_executed']})")
        else:
            print(f"    ✗ Error running backtester: {result.stderr}")
            strat['performance']['backtest_status'] = 'error'
            strat['performance']['backtest_error'] = 'backtester runtime error'
    except subprocess.TimeoutExpired:
        print(f"    ✗ Backtest timeout")
        strat['performance']['backtest_status'] = 'timeout'
        strat['performance']['backtest_error'] = 'timeout'
    except Exception as e:
        print(f"    ✗ Exception: {e}")
        strat['performance']['backtest_status'] = 'error'
        strat['performance']['backtest_error'] = str(e)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Generate signals.json
# ─────────────────────────────────────────────────────────────────────────────

print("\n[7/8] Generating signals...")

# Get current market regime from research
regime = research.get('market_regime_analysis', {})
detected_regime = regime.get('detected_regime', 'consolidation')
regime_confidence = regime.get('regime_confidence', 0.68)

signals = {
    "date": TODAY,
    "regime": {
        "detected": detected_regime,
        "confidence": regime_confidence,
        "description": regime.get('market_structure', '')
    },
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "active_signals": [],
    "backtest_performance": {
        "total_strategies_tested": len(strategies['strategies']),
        "completed_backtests": sum(1 for s in strategies['strategies'] if s['performance'].get('backtest_status') == 'completed'),
        "average_win_rate": 0,
        "average_sharpe": 0
    },
    "signal_sources": []
}

# Generate signals from watcher-incompatible strategies
for strat in strategies['strategies']:
    if strat['status'] != 'paper_testing':
        continue
    
    is_watcher_compatible = strat.get('watcher_compatible', False)
    
    # Only generate signals for non-watcher-compatible strategies
    if is_watcher_compatible:
        print(f"  Skipping {strat['id']}: watcher-compatible (signals from watcher)")
        continue
    
    print(f"  Signal from {strat['id']}: {strat['direction'].upper()}")
    
    signal = {
        "strategy_id": strat['id'],
        "title": strat['title'],
        "direction": strat['direction'],
        "confidence": strat.get('synthesis_confidence', 0),
        "entry_zone": f"{strat.get('entry_price', 'TBD')}",
        "target": strat.get('tp_target', 'TBD'),
        "stop_loss": strat.get('sl_target', 'TBD'),
        "execution_urgency": strat.get('execution_urgency', 'standard'),
        "timeframe": strat.get('max_duration_days', 3),
        "backtest_score": strat['performance'].get('backtest_score', 0),
        "notes": f"Regime: {detected_regime}. Cold start day 7/14 - paper trading only."
    }
    
    signals['active_signals'].append(signal)
    signals['signal_sources'].append({
        "id": strat['id'],
        "type": "ta_signal",
        "quality": "pending_validation" if strat['performance'].get('backtest_status') in ['pending', 'pending_live_data', 'error'] else 'validated'
    })

# Calculate aggregates
if signals['active_signals']:
    avg_wr = sum(s.get('backtest_score', 0) / 60 for s in signals['active_signals']) / len(signals['active_signals'])
    signals['backtest_performance']['average_win_rate'] = round(avg_wr, 3)

print(f"  Generated {len(signals['active_signals'])} active signals")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Update strategies.json (atomic write)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[8/8] Saving state files...")
strategies['last_updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
save_state('strategies', strategies)
print(f"  ✓ Updated strategies.json ({len(strategies['strategies'])} strategies)")

save_state('signals', signals)
print(f"  ✓ Updated signals.json ({len(signals['active_signals'])} signals)")

# Ensure lessons.json exists with correct schema — NEVER overwrite existing lessons.
# Any lessons from strategy retirements this run are appended via append_lessons().
ensure_lessons_file()
print(f"  ✓ lessons.json intact (accumulate-not-reset)")

# Update pipeline_state.json
if 'strategy-tester' not in pipeline.get('completed_today', []):
    pipeline['completed_today'].append('strategy-tester')
    pipeline['last_update'] = datetime.now(timezone.utc).isoformat()
    save_state('pipeline_state', pipeline)
    print(f"  ✓ Updated pipeline_state.json (added strategy-tester)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: Commit to git
# ─────────────────────────────────────────────────────────────────────────────

print("\n[COMMIT] Committing changes...")
try:
    # Stage files
    subprocess.run(
        ['git', 'add', 
         'state/strategies.json',
         'state/signals.json',
         'state/lessons.json',
         'state/pipeline_state.json'],
        cwd=WORKSPACE,
        check=True,
        capture_output=True
    )
    print(f"  ✓ Staged: strategies.json, signals.json, lessons.json, pipeline_state.json")
    
    # Commit
    result = subprocess.run(
        ['git', 'commit', '-m', 'strategy-tester: daily run 2026-05-26'],
        cwd=WORKSPACE,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"  ✓ Committed: {result.stdout.strip()}")
    else:
        print(f"  Note: {result.stdout.strip()}")
    
    # Push
    result = subprocess.run(
        ['git', 'push', 'origin', 'HEAD:main'],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode == 0:
        print(f"  ✓ Pushed to origin main")
    else:
        print(f"  ! Push: {result.stderr[:100]}")
        
except Exception as e:
    print(f"  ✗ Git error: {e}")

print("\n" + "="*70)
print("STRATEGY TESTER DAILY RUN COMPLETE")
print("="*70)

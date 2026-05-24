#!/usr/bin/env python3
import os, json, time
from datetime import datetime, timezone

B = os.path.expanduser('~/btc-agents')

def load(path, default=None):
    try:
        with open(path) as f: return json.load(f)
    except: return default or {}

def eval_condition(cond):
    try:
        data = load(cond['source'])
        val = data
        for key in cond['field'].split('.'):
            val = val.get(key) if isinstance(val, dict) else val
        val = float(val)
        t = float(cond['value'])
        op = cond['operator']
        return (op=='<' and val<t) or (op=='>' and val>t) or \
               (op=='<=' and val<=t) or (op=='>=' and val>=t) or \
               (op=='==' and abs(val-t)<0.001)
    except: return False

print("Signal Watcher starting...")
while True:
    try:
        directive = load(f'{B}/state/orchestrator-directive.json', {})
        if directive.get('signal_watcher_paused'): time.sleep(300); continue
        anomaly = load(f'{B}/state/anomaly_state.json', {})
        if anomaly.get('auto_pause_signal_watcher'): time.sleep(300); continue
        portfolio = load(f'{B}/state/portfolio.json', {})
        if portfolio.get('circuit_breaker_tripped'): time.sleep(300); continue

        strategies = load(f'{B}/state/strategies.json', {}).get('strategies', [])
        live_triggers = load(f'{B}/signals/live_triggers.json', {'triggers':[]})
        fired_recently = {t['strategy_id']: t.get('fired_at') for t in live_triggers.get('triggers',[])}

        new_triggers = []
        for strat in strategies:
            if strat.get('status') not in ('ready_to_trade','active'): continue
            if not strat.get('watcher_compatible'): continue
            if strat.get('consecutive_losses', 0) >= 3: continue
            if strat.get('status') == 'suspended': continue

            last = fired_recently.get(strat['id'])
            if last:
                try:
                    elapsed = time.time() - datetime.fromisoformat(last.replace('Z','+00:00')).timestamp()
                    if elapsed < 14400: continue
                except: pass

            conditions = strat.get('entry_conditions', [])
            logic = strat.get('entry_logic', 'ALL')
            results = [eval_condition(c) for c in conditions]
            triggered = all(results) if logic=='ALL' else any(results)

            if triggered:
                tid = f"trig_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{strat['id'][-4:]}"
                new_triggers.append({'trigger_id': tid,
                    'hypothesis_chain_id': strat.get('hypothesis_chain_id',''),
                    'strategy_id': strat['id'],
                    'fired_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'conditions_met': conditions, 'status': 'pending'})

        if new_triggers:
            existing = live_triggers.get('triggers', [])
            existing.extend(new_triggers)
            tmp = f'{B}/signals/live_triggers.json.tmp'
            with open(tmp,'w') as f: json.dump({'triggers': existing}, f, indent=2)
            os.rename(tmp, f'{B}/signals/live_triggers.json')
            print(f"signal_watcher: {len(new_triggers)} trigger(s) fired")
    except Exception as e: print(f"watcher error: {e}")
    time.sleep(300)

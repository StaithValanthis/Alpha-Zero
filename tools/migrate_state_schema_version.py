#!/usr/bin/env python3
"""One-shot migration: stamp schema_version on all existing state files."""
import sys, json, os
from pathlib import Path

BASE = Path(os.path.expanduser('~/btc-agents'))
sys.path.insert(0, str(BASE))
from tools._state_utils import SCHEMA_VERSIONS, _atomic_write

STATE_DIR = BASE / 'state'

for name, version in SCHEMA_VERSIONS.items():
    path = STATE_DIR / f'{name}.json'
    if not path.exists():
        print(f'  SKIP (missing): {name}.json')
        continue
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print(f'  SKIP (not dict): {name}.json')
        continue
    if data.get('schema_version') == version:
        print(f'  OK (already {version}): {name}.json')
        continue
    old = data.get('schema_version', 'MISSING')
    data['schema_version'] = version
    _atomic_write(path, data)
    print(f'  MIGRATED {old} -> {version}: {name}.json')

print('Migration complete.')

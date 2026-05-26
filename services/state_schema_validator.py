#!/usr/bin/env python3
"""
State schema validator — no-LLM daily watchdog.

Reads every JSON file in state/, validates against state_schemas/<name>.json,
and prints a report ONLY if violations are found.
Hermes no_agent delivery: silent on clean runs, Discord alert on violations.

Exit 0 always (non-zero would send an error alert even on clean days).
"""
import json, os, sys, logging
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(os.path.expanduser('~/btc-agents'))
STATE_DIR = BASE / 'state'
SCHEMA_DIR = BASE / 'state_schemas'

sys.path.insert(0, str(BASE))
from tools._state_utils import SCHEMA_VERSIONS

logging.basicConfig(level=logging.WARNING, format='%(message)s')


def _load_schema(name: str):
    p = SCHEMA_DIR / f'{name}.json'
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def _validate(data, schema) -> list:
    try:
        import jsonschema
        errs = list(jsonschema.Draft7Validator(schema).iter_errors(data))
        return [f'{e.json_path}: {e.message}' for e in errs]
    except Exception as e:
        return [f'validator error: {e}']


def main():
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    violations = []
    missing_schema_version = []
    unreadable = []

    for name, expected_version in SCHEMA_VERSIONS.items():
        path = STATE_DIR / f'{name}.json'
        if not path.exists():
            continue  # Missing files are a separate concern (pipeline failures)

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            unreadable.append(f'  {name}.json: cannot parse — {e}')
            continue

        if not isinstance(data, dict):
            violations.append(f'  {name}.json: root is {type(data).__name__}, expected object')
            continue

        actual_version = data.get('schema_version')
        if actual_version is None:
            missing_schema_version.append(f'  {name}.json: schema_version missing (expected "{expected_version}")')
        elif actual_version != expected_version:
            violations.append(
                f'  {name}.json: schema_version="{actual_version}" expected "{expected_version}"'
            )

        schema = _load_schema(name)
        if schema:
            errs = _validate(data, schema)
            for e in errs:
                violations.append(f'  {name}.json: {e}')

    all_issues = violations + missing_schema_version + unreadable

    if not all_issues:
        # Silent — Hermes no_agent does not deliver empty stdout
        sys.exit(0)

    lines = [
        f'STATE SCHEMA VIOLATIONS — {now}',
        f'({len(violations)} violations, {len(missing_schema_version)} missing version, {len(unreadable)} unreadable)',
        '',
    ]
    if violations:
        lines.append('Schema violations:')
        lines.extend(violations)
    if missing_schema_version:
        lines.append('')
        lines.append('Missing schema_version (run tools/migrate_state_schema_version.py to fix):')
        lines.extend(missing_schema_version)
    if unreadable:
        lines.append('')
        lines.append('Unreadable files:')
        lines.extend(unreadable)
    lines += [
        '',
        'Fix: cd ~/btc-agents && venv/bin/python3 tools/migrate_state_schema_version.py',
    ]
    print('\n'.join(lines))


if __name__ == '__main__':
    main()

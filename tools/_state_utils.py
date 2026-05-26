#!/usr/bin/env python3
"""
State file utilities for the BTC accumulation system.

Every state file that agents read or write must go through these helpers.
They enforce:
  - Atomic writes (no partial files)
  - schema_version stamped on every write
  - jsonschema validation against state_schemas/<name>.json
  - Accumulate-never-reset semantics for append-only files (lessons.json)

Usage:
    from tools._state_utils import load_state, save_state, append_lessons

    # Load with schema validation
    lessons = load_state('lessons')

    # Append a lesson (never overwrites)
    append_lessons(new_lesson_dict)

    # Save with validation
    save_state('strategies', strategies_dict)
"""

import json
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Resolve paths relative to this file (tools/ is inside ~/btc-agents/)
_TOOLS_DIR = Path(__file__).parent
_BASE = _TOOLS_DIR.parent
_STATE_DIR = _BASE / 'state'
_SCHEMA_DIR = _BASE / 'state_schemas'

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema version registry — maps file name (without .json) to current version
# ---------------------------------------------------------------------------
SCHEMA_VERSIONS = {
    'lessons':                     '1.0',
    'strategies':                  '1.0',
    'signals':                     '1.0',
    'pipeline_state':              '1.0',
    'orchestrator-directive':      '1.0',
    'research':                    '1.0',
    'regime_state':                '1.0',
    'weekly-review':               '1.0',
    'anomaly_state':               '1.0',
    'portfolio':                   '1.0',
    'system-log':                  '1.0',
    'system_state':                '1.0',
    'chief_triage':                '1.0',
    'orchestrator-strategy-actions': '1.0',
    'watchlist':                   '1.0',
    'symbol_watchlist':            '1.0',
}


def _schema_path(name: str) -> Optional[Path]:
    p = _SCHEMA_DIR / f'{name}.json'
    return p if p.exists() else None


def _load_schema(name: str) -> Optional[dict]:
    p = _schema_path(name)
    if p is None:
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f'_state_utils: could not load schema {name}: {e}')
        return None


def _validate(data: Any, name: str) -> list[str]:
    """Validate data against schema. Returns list of error strings (empty = valid)."""
    schema = _load_schema(name)
    if schema is None:
        return []   # No schema file yet — skip validation, don't block writes
    try:
        import jsonschema
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(data))
        return [f'{e.json_path}: {e.message}' for e in errors]
    except ImportError:
        logger.warning('_state_utils: jsonschema not installed, skipping validation')
        return []
    except Exception as e:
        logger.warning(f'_state_utils: validation error for {name}: {e}')
        return []


def _atomic_write(path: Path, data: Any) -> None:
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, default=str)
        f.write('\n')
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_state(name: str, default: Any = None) -> Any:
    """
    Load state/<name>.json.
    Returns default if file is missing or unparseable.
    Logs a warning if schema_version is absent or mismatched.
    """
    path = _STATE_DIR / f'{name}.json'
    if not path.exists():
        if default is not None:
            return default
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f'_state_utils: failed to load {name}.json: {e}')
        return default

    if isinstance(data, dict):
        expected = SCHEMA_VERSIONS.get(name)
        actual = data.get('schema_version')
        if expected and actual is None:
            logger.warning(
                f'_state_utils: {name}.json missing schema_version (expected {expected}) — '
                f'file was written before schema enforcement. Reading anyway.'
            )
        elif expected and actual != expected:
            logger.warning(
                f'_state_utils: {name}.json schema_version={actual!r} expected {expected!r}. '
                f'May be a stale write. Reading anyway.'
            )

    return data


def save_state(name: str, data: Any, strict: bool = False) -> None:
    """
    Validate data against schema, stamp schema_version, then atomically write
    state/<name>.json.

    If strict=True and validation errors exist, raises ValueError instead of
    writing. Default (False) logs errors and writes anyway so a bad run doesn't
    leave state files unwritten.
    """
    if isinstance(data, dict):
        version = SCHEMA_VERSIONS.get(name)
        if version:
            data['schema_version'] = version

    errors = _validate(data, name)
    if errors:
        msg = f'_state_utils: {name}.json validation errors:\n' + '\n'.join(f'  {e}' for e in errors)
        if strict:
            raise ValueError(msg)
        logger.error(msg)

    path = _STATE_DIR / f'{name}.json'
    _atomic_write(path, data)


def append_lessons(new_lesson: dict, recurring_update: Optional[str] = None, worked_update: Optional[str] = None) -> None:
    """
    Append a lesson to lessons.json. NEVER resets existing lessons.

    Args:
        new_lesson: Dict conforming to lessons schema (lesson_id, date, lesson_type, ...)
        recurring_update: If set, append this string to recurring_failure_patterns
        worked_update:    If set, append this string to what_has_worked
    """
    existing = load_state('lessons') or _empty_lessons()

    # Ensure required arrays exist (migrate from old schema if needed)
    if not isinstance(existing.get('lessons'), list):
        existing['lessons'] = []
    if not isinstance(existing.get('recurring_failure_patterns'), list):
        existing['recurring_failure_patterns'] = []
    if not isinstance(existing.get('what_has_worked'), list):
        existing['what_has_worked'] = []
    if not isinstance(existing.get('regression_tests'), list):
        existing['regression_tests'] = []
    if not isinstance(existing.get('strategy_feedback'), list):
        existing['strategy_feedback'] = []

    # Assign a lesson_id if missing
    if 'lesson_id' not in new_lesson:
        today = datetime.now(timezone.utc).strftime('%Y%m%d')
        idx = sum(1 for l in existing['lessons'] if today in l.get('lesson_id', '')) + 1
        new_lesson['lesson_id'] = f'lesson_{today}_{idx:03d}'

    # Deduplicate by lesson_id
    existing_ids = {l.get('lesson_id') for l in existing['lessons']}
    if new_lesson.get('lesson_id') in existing_ids:
        logger.info(f"_state_utils: lesson {new_lesson['lesson_id']} already exists, skipping")
        return

    existing['lessons'].append(new_lesson)
    existing['last_updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    if recurring_update and recurring_update not in existing['recurring_failure_patterns']:
        existing['recurring_failure_patterns'].append(recurring_update)
    if worked_update and worked_update not in existing['what_has_worked']:
        existing['what_has_worked'].append(worked_update)

    save_state('lessons', existing)


def ensure_lessons_file() -> dict:
    """
    Return existing lessons.json or create it with the canonical empty schema.
    Does NOT overwrite if it already exists. Safe to call on every run.
    """
    existing = load_state('lessons')
    if existing is None:
        existing = _empty_lessons()
        save_state('lessons', existing)
    return existing


def _empty_lessons() -> dict:
    return {
        'schema_version': SCHEMA_VERSIONS['lessons'],
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'lessons': [],
        'recurring_failure_patterns': [],
        'what_has_worked': [],
        'regression_tests': [],
        'strategy_feedback': [],
    }


if __name__ == '__main__':
    # Quick self-test — monkey-patch paths to a temp dir
    import tempfile, shutil, types
    test_base = Path(tempfile.mkdtemp())
    (test_base / 'state').mkdir()
    (test_base / 'state_schemas').mkdir()

    import sys as _sys
    _mod = _sys.modules[__name__]
    _mod._STATE_DIR = test_base / 'state'
    _mod._SCHEMA_DIR = test_base / 'state_schemas'

    # Test ensure_lessons_file creates file
    l = ensure_lessons_file()
    assert l['lessons'] == [], f'lessons should be empty, got {l["lessons"]}'
    assert l['schema_version'] == '1.0', 'schema_version should be 1.0'

    # Test append_lessons accumulates
    append_lessons({'lesson_id': 'lesson_test_001', 'date': '2026-01-01',
                    'lesson_type': 'strategy', 'actionable_takeaway': 'test'})
    append_lessons({'lesson_id': 'lesson_test_002', 'date': '2026-01-02',
                    'lesson_type': 'strategy', 'actionable_takeaway': 'test2'})

    # Test idempotent (same ID not added twice)
    append_lessons({'lesson_id': 'lesson_test_001', 'date': '2026-01-01',
                    'lesson_type': 'strategy', 'actionable_takeaway': 'test'})

    l2 = load_state('lessons')
    assert len(l2['lessons']) == 2, f'Expected 2 lessons, got {len(l2["lessons"])}'
    print('_state_utils self-test: PASS')
    shutil.rmtree(test_base)

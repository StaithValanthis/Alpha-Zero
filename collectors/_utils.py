import json, os, time
from datetime import datetime, timezone

def atomic_write(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.rename(tmp, path)

def envelope(collector, data, stale_after=3600):
    return {"schema_version": "1.0", "collector": collector,
            "collected_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            "stale_after_seconds": stale_after, "data": data}

def load_env():
    env = {}
    with open(os.path.expanduser('~/btc-agents/.env')) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); env[k.strip()] = v.strip()
    return env

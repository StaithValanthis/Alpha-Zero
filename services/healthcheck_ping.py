#!/usr/bin/env python3
import requests, os

env = {}
with open(os.path.expanduser('~/btc-agents/.env')) as f:
    for line in f:
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            k, v = line.split('=',1); env[k.strip()] = v.strip()

uuid = env.get('HEALTHCHECKS_UUID','')
if uuid:
    try: requests.get(f'https://hc-ping.com/{uuid}', timeout=5); print("ping: OK")
    except Exception as e: print(f"ping failed: {e}")

#!/usr/bin/env python3
import shutil, requests, os

env = {}
with open(os.path.expanduser('~/btc-agents/.env')) as f:
    for line in f:
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            k, v = line.split('=',1); env[k.strip()] = v.strip()

total, used, free = shutil.disk_usage(os.path.expanduser('~/btc-agents'))
pct = (used/total)*100
if pct >= 80:
    wh = env.get('DISCORD_WEBHOOK_URL','')
    if wh: requests.post(wh, json={"embeds":[{"title":"WARNING — Disk space",
        "description":f"Disk {pct:.1f}% full. Free: {free//1024//1024//1024:.1f}GB",
        "color":16776960}]}, timeout=5)
    print(f"disk_monitor: WARNING {pct:.1f}%")
else: print(f"disk_monitor: OK {pct:.1f}%")

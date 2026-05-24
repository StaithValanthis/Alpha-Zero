#!/usr/bin/env python3
import sys, os, requests
sys.path.insert(0, os.path.dirname(__file__))
from _utils import atomic_write, envelope

B = os.path.expanduser('~/btc-agents')
r = requests.get('https://api.alternative.me/fng/?limit=7', timeout=10)
atomic_write(f'{B}/data/macro/fear_greed_7d.json', envelope('fear_greed', r.json().get('data',[]), 86400))
print("fear_greed: OK")

"""
Discord notification utilities for BTC Agent.
Provides standard webhook posting and bot-API posting with interactive buttons.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv('/home/btc-agent/btc-agents/.env')

WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN', '')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID', '')
DISCORD_API = 'https://discord.com/api/v10'


def _post_json(url: str, payload: dict, headers: dict = None) -> dict:
    data = json.dumps(payload).encode('utf-8')
    default_headers = {'Content-Type': 'application/json', 'User-Agent': 'BTC-Agent/1.0'}
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=default_headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Discord API {e.code}: {body}') from e


def post_webhook(payload: dict) -> bool:
    """Post any payload to the Discord webhook (no buttons support)."""
    if not WEBHOOK_URL:
        return False
    _post_json(WEBHOOK_URL, payload)
    return True


def post_embed(title: str, description: str = '', color: int = 0xffa500, fields: list = None) -> bool:
    """Post a simple embed via webhook."""
    embed = {'title': title, 'description': description, 'color': color}
    if fields:
        embed['fields'] = fields
    return post_webhook({'embeds': [embed]})


def post_proposal_with_buttons(proposal_id: str, proposal_data: dict) -> dict:
    """
    Post a proposal embed with Approve/Reject buttons via the Bot API.
    Buttons only work when posted by a bot (not a webhook), so this uses
    the Bot API directly against DISCORD_CHANNEL_ID.

    Returns the Discord message object dict on success.
    Raises RuntimeError on failure.
    """
    if not BOT_TOKEN:
        raise RuntimeError('DISCORD_BOT_TOKEN not set')
    if not CHANNEL_ID:
        raise RuntimeError('DISCORD_CHANNEL_ID not set')

    agent_name = proposal_data.get('agent_name', 'unknown')
    agent_role = proposal_data.get('agent_role', '')
    problem = proposal_data.get('problem_statement', '')
    if isinstance(problem, str):
        problem = problem.strip()
    cost = proposal_data.get('estimated_cost_per_day', '?')
    evidence = proposal_data.get('evidence', [])
    created = proposal_data.get('created_date', datetime.now(timezone.utc).strftime('%Y-%m-%d'))

    evidence_str = '\n'.join(f'• {e}' for e in evidence[:4]) if evidence else '_No evidence listed_'

    embed = {
        'title': '🔔 Chief Evaluation — New Agent Proposal',
        'color': 0xffa500,  # amber
        'fields': [
            {'name': 'Proposal ID', 'value': f'`{proposal_id}`', 'inline': True},
            {'name': 'Agent Name', 'value': agent_name, 'inline': True},
            {'name': 'Estimated Cost', 'value': f'${cost}/day', 'inline': True},
            {'name': 'Role', 'value': agent_role, 'inline': False},
            {'name': 'Problem Statement', 'value': problem[:1024], 'inline': False},
            {'name': 'Evidence', 'value': evidence_str[:1024], 'inline': False},
        ],
        'footer': {'text': f'Created {created} | Tap a button or use /approve /reject'},
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }

    components = [
        {
            'type': 1,  # ACTION_ROW
            'components': [
                {
                    'type': 2,  # BUTTON
                    'style': 3,  # SUCCESS (green)
                    'label': '✅ Approve',
                    'custom_id': f'approve_{proposal_id}',
                },
                {
                    'type': 2,  # BUTTON
                    'style': 4,  # DANGER (red)
                    'label': '❌ Reject',
                    'custom_id': f'reject_{proposal_id}',
                },
            ],
        }
    ]

    payload = {'embeds': [embed], 'components': components}
    headers = {'Authorization': f'Bot {BOT_TOKEN}'}
    url = f'{DISCORD_API}/channels/{CHANNEL_ID}/messages'

    result = _post_json(url, payload, headers)
    return result

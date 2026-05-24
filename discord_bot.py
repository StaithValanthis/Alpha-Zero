"""
BTC Agent Discord Bot
Handles Approve/Reject button interactions and slash commands for proposal management.
"""

import os
import json
import yaml
import shutil
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv('/home/btc-agent/btc-agents/.env')

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '0'))
BASE_DIR = Path('/home/btc-agent/btc-agents')
LOG_FILE = BASE_DIR / 'logs' / 'discord_bot.log'

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

PROPOSALS_DIR = BASE_DIR / 'proposals'
PENDING_DIR = PROPOSALS_DIR / 'pending'
APPROVED_DIR = PROPOSALS_DIR / 'approved'
REJECTED_DIR = PROPOSALS_DIR / 'rejected'

for d in (PENDING_DIR, APPROVED_DIR, REJECTED_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(action: str, proposal_id: str, username: str):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    logger.info(f'{ts} | {action} | {proposal_id} | {username}')


def _move_proposal(proposal_id: str, destination: Path) -> bool:
    src = PENDING_DIR / f'{proposal_id}.yaml'
    if not src.exists():
        return False
    try:
        shutil.move(str(src), str(destination / f'{proposal_id}.yaml'))
        return True
    except Exception as e:
        logger.error(f'Failed to move {proposal_id}: {e}')
        return False


def _update_proposal_status(proposal_id: str, status: str, dest_dir: Path):
    target = dest_dir / f'{proposal_id}.yaml'
    if not target.exists():
        return
    try:
        with open(target) as f:
            data = yaml.safe_load(f) or {}
        data['status'] = status
        with open(target, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
    except Exception as e:
        logger.warning(f'Could not update status field in {proposal_id}.yaml: {e}')


def _read_pending_proposals() -> list[dict]:
    proposals = []
    for f in sorted(PENDING_DIR.glob('*.yaml')):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh) or {}
            data['_id'] = f.stem
            proposals.append(data)
        except Exception:
            pass
    return proposals


def _read_system_status() -> dict:
    status = {}
    try:
        with open(BASE_DIR / 'state' / 'portfolio.json') as f:
            portfolio = json.load(f)
        status['demo_mode'] = portfolio.get('demo_mode', 'unknown')
        status['open_positions'] = len(portfolio.get('open_positions', []))
    except Exception:
        status['demo_mode'] = 'unknown'
        status['open_positions'] = '?'

    try:
        with open(BASE_DIR / 'state' / 'orchestrator-directive.json') as f:
            directive = json.load(f)
        status['focus_area'] = directive.get('focus_area', 'unknown')
        status['alt_rotation_active'] = directive.get('alt_rotation_active', False)
        status['signal_watcher_paused'] = directive.get('signal_watcher_paused', False)
    except Exception:
        status['focus_area'] = 'unknown'
        status['alt_rotation_active'] = '?'
        status['signal_watcher_paused'] = '?'

    try:
        with open(BASE_DIR / 'data' / 'meta' / 'collection_status.json') as f:
            col = json.load(f)
        collectors = col.get('collectors', {})
        green = sum(1 for v in collectors.values() if v.get('health') == 'green')
        red = sum(1 for v in collectors.values() if v.get('health') != 'green')
        status['collectors_green'] = green
        status['collectors_red'] = red
    except Exception:
        status['collectors_green'] = '?'
        status['collectors_red'] = '?'

    return status


async def _disable_buttons(message: discord.Message):
    """Rebuild the view with all buttons disabled."""
    try:
        view = discord.ui.View()
        for action_row in message.components:
            for comp in action_row.children:
                btn = discord.ui.Button(
                    label=comp.label,
                    style=comp.style,
                    custom_id=comp.custom_id,
                    disabled=True,
                )
                view.add_item(btn)
        await message.edit(view=view)
    except Exception as e:
        logger.warning(f'Could not disable buttons: {e}')


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!btc-', intents=intents)


@bot.event
async def on_ready():
    logger.info(f'Discord bot ready: {bot.user} (id={bot.user.id})')
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    try:
        synced = await bot.tree.sync(guild=guild)
        logger.info(f'Synced {len(synced)} slash commands to guild {GUILD_ID}')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')


# ---------------------------------------------------------------------------
# Button interaction handler
# ---------------------------------------------------------------------------

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get('custom_id', '')
    if not (custom_id.startswith('approve_') or custom_id.startswith('reject_')):
        return

    parts = custom_id.split('_', 1)
    if len(parts) != 2:
        return

    action, proposal_id = parts[0], parts[1]
    username = str(interaction.user)
    now_str = datetime.now(timezone.utc).strftime('%H:%M UTC')

    if action == 'approve':
        await _handle_approve(interaction, proposal_id, username, now_str)
    elif action == 'reject':
        await _handle_reject(interaction, proposal_id, username, now_str)


async def _handle_approve(
    interaction: discord.Interaction,
    proposal_id: str,
    username: str,
    now_str: str,
):
    await interaction.response.defer(ephemeral=True)

    if not (PENDING_DIR / f'{proposal_id}.yaml').exists():
        await interaction.followup.send(
            f'⚠️ Proposal `{proposal_id}` not found in pending/', ephemeral=True
        )
        return

    if not _move_proposal(proposal_id, APPROVED_DIR):
        await interaction.followup.send(
            f'⚠️ Failed to move `{proposal_id}` — check server logs', ephemeral=True
        )
        return

    _update_proposal_status(proposal_id, 'approved', APPROVED_DIR)
    _log('APPROVE', proposal_id, username)

    # Edit original message embed to green with approval field
    try:
        msg = interaction.message
        if msg and msg.embeds:
            embed = msg.embeds[0].copy()
            embed.color = discord.Color.green()
            embed.add_field(name='✅ Approved by', value=f'{username} at {now_str}', inline=False)
            await _disable_buttons(msg)
            await msg.edit(embed=embed)
    except Exception as e:
        logger.warning(f'Could not update embed for {proposal_id}: {e}')

    await interaction.followup.send(
        f'✅ `{proposal_id}` approved by {username} — deployer will pick this up within the hour',
        ephemeral=False
    )


async def _handle_reject(
    interaction: discord.Interaction,
    proposal_id: str,
    username: str,
    now_str: str,
):
    await interaction.response.defer(ephemeral=True)

    if not (PENDING_DIR / f'{proposal_id}.yaml').exists():
        await interaction.followup.send(
            f'⚠️ Proposal `{proposal_id}` not found in pending/', ephemeral=True
        )
        return

    if not _move_proposal(proposal_id, REJECTED_DIR):
        await interaction.followup.send(
            f'⚠️ Failed to move `{proposal_id}` — check server logs', ephemeral=True
        )
        return

    _update_proposal_status(proposal_id, 'rejected', REJECTED_DIR)
    _log('REJECT', proposal_id, username)

    try:
        msg = interaction.message
        if msg and msg.embeds:
            embed = msg.embeds[0].copy()
            embed.color = discord.Color.red()
            embed.add_field(name='❌ Rejected by', value=f'{username} at {now_str}', inline=False)
            await _disable_buttons(msg)
            await msg.edit(embed=embed)
    except Exception as e:
        logger.warning(f'Could not update embed for {proposal_id}: {e}')

    await interaction.followup.send(
        f'❌ `{proposal_id}` rejected by {username}',
        ephemeral=False
    )


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(name='approve', description='Approve a pending proposal')
@app_commands.describe(proposal_id='Proposal ID, e.g. prop_20260524_001')
async def slash_approve(interaction: discord.Interaction, proposal_id: str):
    username = str(interaction.user)
    now_str = datetime.now(timezone.utc).strftime('%H:%M UTC')

    if not (PENDING_DIR / f'{proposal_id}.yaml').exists():
        await interaction.response.send_message(
            f'⚠️ Proposal `{proposal_id}` not found in pending/', ephemeral=True
        )
        return

    if not _move_proposal(proposal_id, APPROVED_DIR):
        await interaction.response.send_message(
            f'⚠️ Failed to move `{proposal_id}` — check server logs', ephemeral=True
        )
        return

    _update_proposal_status(proposal_id, 'approved', APPROVED_DIR)
    _log('APPROVE (slash)', proposal_id, username)

    await interaction.response.send_message(
        f'✅ `{proposal_id}` approved by {username} at {now_str} — deployer picks up within the hour',
        ephemeral=True
    )


@bot.tree.command(name='reject', description='Reject a pending proposal')
@app_commands.describe(proposal_id='Proposal ID, e.g. prop_20260524_001')
async def slash_reject(interaction: discord.Interaction, proposal_id: str):
    username = str(interaction.user)
    now_str = datetime.now(timezone.utc).strftime('%H:%M UTC')

    if not (PENDING_DIR / f'{proposal_id}.yaml').exists():
        await interaction.response.send_message(
            f'⚠️ Proposal `{proposal_id}` not found in pending/', ephemeral=True
        )
        return

    if not _move_proposal(proposal_id, REJECTED_DIR):
        await interaction.response.send_message(
            f'⚠️ Failed to move `{proposal_id}` — check server logs', ephemeral=True
        )
        return

    _update_proposal_status(proposal_id, 'rejected', REJECTED_DIR)
    _log('REJECT (slash)', proposal_id, username)

    await interaction.response.send_message(
        f'❌ `{proposal_id}` rejected by {username} at {now_str}',
        ephemeral=True
    )


@bot.tree.command(name='proposals', description='List all pending proposals')
async def slash_proposals(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    proposals = _read_pending_proposals()
    if not proposals:
        await interaction.followup.send('No pending proposals.', ephemeral=True)
        return

    embed = discord.Embed(
        title=f'Pending Proposals ({len(proposals)})',
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    for p in proposals[:25]:  # Discord limit
        pid = p.get('_id', '?')
        agent = p.get('agent_name', '?')
        role = p.get('agent_role', '?')
        problem = p.get('problem_statement', '')
        if isinstance(problem, str):
            problem = problem.strip()[:120]
        cost = p.get('estimated_cost_per_day', '?')
        embed.add_field(
            name=f'`{pid}` — {agent}',
            value=f'**Role:** {role}\n**Cost:** ${cost}/day\n**Problem:** {problem}…',
            inline=False,
        )

    embed.set_footer(text='Use /approve <id> or /reject <id> to act')
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name='status', description='Quick system health check')
async def slash_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    s = _read_system_status()
    pending_count = len(list(PENDING_DIR.glob('*.yaml')))

    demo_emoji = '🔵' if s['demo_mode'] else '🟢'
    paused_emoji = '⏸️' if s['signal_watcher_paused'] else '▶️'
    collectors_line = f"🟢 {s['collectors_green']}  🔴 {s['collectors_red']}"
    alt_emoji = '🔄' if s['alt_rotation_active'] else '—'

    embed = discord.Embed(
        title='BTC Agent System Status',
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name='Mode', value=f"{demo_emoji} {'DEMO' if s['demo_mode'] else 'LIVE'}", inline=True)
    embed.add_field(name='Signal Watcher', value=f'{paused_emoji} {"Paused" if s["signal_watcher_paused"] else "Running"}', inline=True)
    embed.add_field(name='Open Positions', value=str(s['open_positions']), inline=True)
    embed.add_field(name='Focus', value=str(s['focus_area'])[:100], inline=False)
    embed.add_field(name='Alt Rotation', value=f'{alt_emoji} {"Active" if s["alt_rotation_active"] else "Off"}', inline=True)
    embed.add_field(name='Collectors', value=collectors_line, inline=True)
    embed.add_field(name='Pending Proposals', value=str(pending_count), inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if not BOT_TOKEN:
        raise RuntimeError('DISCORD_BOT_TOKEN not set in .env')
    bot.run(BOT_TOKEN, log_handler=None)

"""
llm_router.py — Permanent free LLM routing for BTC Agent System.

All providers are permanently free tiers. No paid models. No Claude.
All chains end with a reliable free fallback (Groq llama-3.3-70b).

VERIFIED WORKING MODELS (tested 2026-05-24):
  Cerebras (free, ~1M tok/day):
    qwen-3-235b-a22b-instruct-2507  — 235B MoE, highest capability available
    llama3.1-8b                     — fast, small, reliable fallback

  Groq (free tier):
    qwen/qwen3-32b                           — strong reasoning, ~44 Intelligence Index
    openai/gpt-oss-120b                      — 120B MoE, reliable mid-tier
    llama-3.3-70b-versatile                  — ~28 Intelligence Index, reliable
    meta-llama/llama-4-scout-17b-16e-instruct — 512K context, fast

  Gemini (Google AI Studio free, 1500 req/day):
    gemini-2.0-flash                         — 1M context, classifier primary

EXCLUDED:
  GLM/Z.ai   — requires paid credit (1113: insufficient balance), NOT free
  zai-glm-4.7 on Cerebras — returns no text content (streaming-only model)
  gpt-oss-120b on Cerebras — returns no text content
  DeepSeek R1 on Groq — decommissioned as of 2026-05-24
  QwQ-32b on Groq — model removed
"""

from __future__ import annotations

import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from openai import OpenAI, APIStatusError, APITimeoutError, APIConnectionError
except ImportError:
    raise ImportError("openai package required: pip install openai")

logger = logging.getLogger(__name__)

# ── Log path ─────────────────────────────────────────────────────────────────
_LOG_PATH = Path(__file__).parent.parent / "logs" / "llm_router.log"
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Timeout per call ─────────────────────────────────────────────────────────
CALL_TIMEOUT_S = 45

# ── Provider connection factories ─────────────────────────────────────────────
def _cerebras() -> OpenAI:
    return OpenAI(
        api_key=os.environ["CEREBRAS_API_KEY"],
        base_url="https://api.cerebras.ai/v1",
    )

def _groq() -> OpenAI:
    return OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )

def _gemini() -> OpenAI:
    return OpenAI(
        api_key=os.environ["GEMINI_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )

# ── Tier definitions ──────────────────────────────────────────────────────────
# Each entry: (provider_label, client_factory, model_id)
# Ordered highest Intelligence Index first; fallback last.
#
# CRITICAL — orchestrator, risk-manager, trader-entry, synthesis, chief
#   Highest-stakes agents. Use the largest available free model first.
_CRITICAL = [
    ("cerebras", _cerebras, "qwen-3-235b-a22b-instruct-2507"),  # 235B, best free
    ("groq",     _groq,     "qwen/qwen3-32b"),                  # Index ~44
    ("groq",     _groq,     "openai/gpt-oss-120b"),             # 120B MoE, reliable
    ("groq",     _groq,     "llama-3.3-70b-versatile"),         # Index ~28, guaranteed
]

# REASONING — bull-researcher, bear-researcher, hypothesis-generator, journal-agent
#   Multi-step reasoning, adversarial debate, hypothesis generation.
_REASONING = [
    ("groq",     _groq,     "qwen/qwen3-32b"),                  # reasoning specialist
    ("cerebras", _cerebras, "qwen-3-235b-a22b-instruct-2507"),  # 235B deep reasoning
    ("groq",     _groq,     "openai/gpt-oss-120b"),             # reliable mid
    ("groq",     _groq,     "llama-3.3-70b-versatile"),         # guaranteed fallback
]

# ANALYST — options-analyst, onchain-macro-analyst, technical-analyst,
#           derivatives-analyst, sentiment-news-analyst
#   Structured data interpretation, signal analysis, JSON output.
_ANALYST = [
    ("cerebras", _cerebras, "qwen-3-235b-a22b-instruct-2507"),  # 235B, strong JSON
    ("groq",     _groq,     "qwen/qwen3-32b"),                  # Index ~44
    ("groq",     _groq,     "llama-3.3-70b-versatile"),         # reliable structured output
    ("groq",     _groq,     "meta-llama/llama-4-scout-17b-16e-instruct"),  # long context
]

# OPS — trader-management, reporter, btc-chief-evaluator, btc-agent-deployer,
#       btc-trigger-queue
#   Mechanical tasks: file ops, threshold checks, Discord formatting, scheduling.
#   Speed over depth; use smaller fast models.
_OPS = [
    ("groq",     _groq,     "llama-3.3-70b-versatile"),                    # fast, reliable
    ("groq",     _groq,     "meta-llama/llama-4-scout-17b-16e-instruct"),  # long context
    ("cerebras", _cerebras, "llama3.1-8b"),                                # fast, small
]

# CLASSIFIER — news_classifier
#   Needs 1M context for large document sets. Gemini Flash is the only
#   free model with this context window.
_CLASSIFIER = [
    ("gemini", _gemini, "gemini-2.0-flash"),                            # 1M ctx, 1500/day
    ("groq",   _groq,   "meta-llama/llama-4-scout-17b-16e-instruct"),  # 512K fallback
]

_TIERS: dict[str, list] = {
    "critical":   _CRITICAL,
    "reasoning":  _REASONING,
    "analyst":    _ANALYST,
    "ops":        _OPS,
    "classifier": _CLASSIFIER,
}


def call_with_fallback(
    messages: list[dict],
    task_tier: str,
    system_prompt: str | None = None,
    agent_name: str = "unknown",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Call the appropriate model chain for the given tier.

    Args:
        messages:      OpenAI-format message list (without system message).
        task_tier:     One of: critical, reasoning, analyst, ops, classifier.
        system_prompt: Optional system message prepended to messages.
        agent_name:    Name of the calling agent (for logging).
        max_tokens:    Max tokens in response.

    Returns:
        {
          response, provider_used, model_used, fallback_count,
          tokens_input, tokens_output, latency_ms, cost_usd
        }

    Raises:
        RuntimeError if all providers in the chain fail.
        ValueError   if task_tier is unknown.
    """
    if task_tier not in _TIERS:
        raise ValueError(
            f"Unknown task_tier {task_tier!r}. "
            f"Valid: {list(_TIERS)}"
        )

    chain = _TIERS[task_tier]
    full_messages = messages
    if system_prompt:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

    errors: list[str] = []
    fallback_count = 0
    start_total = time.time()

    for provider_label, client_factory, model_id in chain:
        try:
            client = client_factory()
            t0 = time.time()
            resp = client.chat.completions.create(
                model=model_id,
                messages=full_messages,
                max_tokens=max_tokens,
                timeout=CALL_TIMEOUT_S,
            )
            latency_ms = int((time.time() - t0) * 1000)

            content = resp.choices[0].message.content
            if content is None:
                # Some models (zai-glm-4.7) return None content; treat as failure
                raise ValueError(f"Model {model_id} returned null content")

            usage = resp.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()
            result = {
                "response":       content,
                "provider_used":  provider_label,
                "model_used":     model_id,
                "fallback_count": fallback_count,
                "tokens_input":   getattr(usage, "prompt_tokens", 0),
                "tokens_output":  getattr(usage, "completion_tokens", 0),
                "latency_ms":     latency_ms,
                "cost_usd":       0.0,
            }
            _write_log(agent_name, task_tier, result)
            return result

        except (APIStatusError, APITimeoutError, APIConnectionError, ValueError) as exc:
            err_str = str(exc)[:200]
            errors.append(f"{provider_label}/{model_id}: {err_str}")
            logger.warning(
                "LLM router fallback — tier=%s agent=%s failed=%s/%s error=%s",
                task_tier, agent_name, provider_label, model_id, err_str,
            )
            fallback_count += 1
            continue

    total_ms = int((time.time() - start_total) * 1000)
    error_summary = " | ".join(errors)
    raise RuntimeError(
        f"All providers exhausted for tier={task_tier} agent={agent_name} "
        f"after {total_ms}ms. Errors: {error_summary}"
    )


def _write_log(agent_name: str, tier: str, result: dict) -> None:
    """Append one pipe-delimited line to the router log."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"{ts}|{agent_name}|{tier}|{result['provider_used']}|"
        f"{result['model_used']}|{result['fallback_count']}|"
        f"{result['tokens_input']}|{result['tokens_output']}|"
        f"{result['latency_ms']}|cost_usd:0.00\n"
    )
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line)
    except OSError as exc:
        logger.error("Failed to write router log: %s", exc)

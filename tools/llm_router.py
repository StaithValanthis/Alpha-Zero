"""
llm_router.py — Zero-cost LLM fallback router for BTC agent system.

14 tiers, each with a 4-step chain: primary → alt Groq pool → Mistral free → OpenRouter free.
Parallel-pool aware: parallel-running agents never share the same Groq model.

All providers are permanently free. No trial credits. No expiry.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path.home() / "btc-agents" / ".env")

LOG_FILE = Path.home() / "btc-agents" / "logs" / "llm_router.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(message)s",
)

# ── Provider endpoints ──────────────────────────────────────────────────────
_PROVIDERS = {
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "key_env": "CEREBRAS_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
    },
}

# ── Tier chains ─────────────────────────────────────────────────────────────
# Each entry: (provider_key, model_id)
_TIERS: dict[str, list[tuple[str, str]]] = {
    # Highest-stakes: sequential, no parallel contention
    "critical": [
        ("cerebras", "qwen-3-235b-a22b-instruct-2507"),
        ("groq",     "openai/gpt-oss-120b"),
        ("mistral",  "mistral-large-latest"),
        ("openrouter", "minimax/minimax-m2.5:free"),
    ],
    # Bull-researcher: separate Groq pool from bear (llama-4-scout vs gpt-oss-120b)
    "reasoning_bull": [
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("groq",     "openai/gpt-oss-120b"),
        ("mistral",  "mistral-large-latest"),
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ],
    # Bear-researcher: separate Groq pool from bull
    "reasoning_bear": [
        ("groq",     "openai/gpt-oss-120b"),
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("mistral",  "mistral-large-latest"),
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ],
    # Hypothesis-generator: sequential, strong reasoning
    "reasoning_solo": [
        ("groq",     "openai/gpt-oss-120b"),
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("mistral",  "mistral-medium-latest"),
        ("openrouter", "minimax/minimax-m2.5:free"),
    ],
    # Options-analyst: only Cerebras call during morning pipeline
    "analyst_strong": [
        ("cerebras", "qwen-3-235b-a22b-instruct-2507"),
        ("groq",     "openai/gpt-oss-120b"),
        ("mistral",  "mistral-large-latest"),
        ("openrouter", "minimax/minimax-m2.5:free"),
    ],
    # Onchain-macro: gpt-oss-120b pool (parallel with bear/hypothesis)
    "analyst_macro": [
        ("groq",     "openai/gpt-oss-120b"),
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("mistral",  "mistral-medium-latest"),
        ("openrouter", "minimax/minimax-m2.5:free"),
    ],
    # Technical-analyst: llama-4-scout pool (parallel with bull)
    "analyst_technical": [
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("groq",     "openai/gpt-oss-120b"),
        ("mistral",  "mistral-medium-latest"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # Derivatives-analyst: 70b pool, chief shares but calls are tiny
    "analyst_derivatives": [
        ("groq",     "llama-3.3-70b-versatile"),
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("mistral",  "mistral-small-latest"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # Sentiment-news: lightweight synthesis, high-RPM pool
    "analyst_simple": [
        ("groq",     "llama-3.1-8b-instant"),
        ("groq",     "llama-3.3-70b-versatile"),
        ("mistral",  "mistral-small-latest"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # Chief: continuous coordination, short prompts
    "ops_chief": [
        ("groq",     "llama-3.3-70b-versatile"),
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("mistral",  "mistral-small-latest"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # Standard ops: strategy-tester, trader-management, reporter, evaluator
    "ops_standard": [
        ("groq",     "llama-3.3-70b-versatile"),
        ("groq",     "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("mistral",  "mistral-small-latest"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # High-frequency polling: deployer, trigger-queue
    "ops_mechanical": [
        ("groq",     "llama-3.1-8b-instant"),
        ("groq",     "llama-3.3-70b-versatile"),
        ("mistral",  "open-mistral-nemo"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # Classification only
    "classifier": [
        ("gemini",   "gemini-2.0-flash"),
        ("groq",     "llama-3.1-8b-instant"),
        ("mistral",  "mistral-small-latest"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    ],
    # Code generation — free Mistral Experiment tier
    "builder": [
        ("mistral",  "codestral-latest"),
        ("mistral",  "devstral-medium-latest"),
        ("groq",     "openai/gpt-oss-120b"),
        ("openrouter", "minimax/minimax-m2.5:free"),
    ],
}

TIMEOUT_S = 45


def _get_client(provider: str) -> OpenAI:
    cfg = _PROVIDERS[provider]
    api_key = os.getenv(cfg["key_env"])
    if not api_key:
        raise ValueError(f"Missing env var {cfg['key_env']}")
    return OpenAI(api_key=api_key, base_url=cfg["base_url"], timeout=TIMEOUT_S)


def call_with_fallback(
    messages: list[dict],
    task_tier: str,
    system_prompt: str | None = None,
    agent_name: str = "unknown",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Try each provider in the tier chain. Return on first success.
    Raises RuntimeError if all providers fail.
    """
    if task_tier not in _TIERS:
        raise ValueError(f"Unknown tier '{task_tier}'. Valid: {sorted(_TIERS)}")

    chain = _TIERS[task_tier]
    errors: list[str] = []
    fallback_count = 0

    full_messages = messages
    if system_prompt:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

    for provider, model in chain:
        try:
            client = _get_client(provider)
            t0 = time.time()
            resp = client.chat.completions.create(
                model=model,
                messages=full_messages,
                max_tokens=max_tokens,
            )
            latency_ms = int((time.time() - t0) * 1000)

            content = resp.choices[0].message.content
            if content is None:
                raise ValueError(f"Null content from {provider}/{model} "
                                 f"(finish_reason={resp.choices[0].finish_reason})")

            tok_in = getattr(resp.usage, "prompt_tokens", 0) or 0
            tok_out = getattr(resp.usage, "completion_tokens", 0) or 0

            _log(agent_name, task_tier, provider, model,
                 fallback_count, tok_in, tok_out, latency_ms)

            return {
                "response": content,
                "provider_used": provider,
                "model_used": model,
                "fallback_count": fallback_count,
                "tokens_input": tok_in,
                "tokens_output": tok_out,
                "latency_ms": latency_ms,
                "cost_usd": 0.00,
            }

        except Exception as exc:
            err_str = str(exc)[:200]
            errors.append(f"{provider}/{model}: {err_str}")
            # Only retry on rate-limit (429) or timeout — fail fast on auth/bad-model
            if "401" in err_str or "403" in err_str:
                break
            fallback_count += 1

    raise RuntimeError(
        f"All providers exhausted for tier '{task_tier}' agent '{agent_name}'.\n"
        + "\n".join(errors)
    )


def _log(agent: str, tier: str, provider: str, model: str,
         fallbacks: int, tok_in: int, tok_out: int, latency_ms: int) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = (f"{ts}|{agent}|{tier}|{provider}|{model}|"
            f"{fallbacks}|{tok_in}|{tok_out}|{latency_ms}|cost_usd:0.00")
    logging.info(line)


if __name__ == "__main__":
    import sys
    tier = sys.argv[1] if len(sys.argv) > 1 else "ops_standard"
    result = call_with_fallback(
        messages=[{"role": "user", "content": "Reply with OK only"}],
        task_tier=tier,
        system_prompt="You are a test. Reply with OK only.",
        agent_name="test",
    )
    print(f"provider={result['provider_used']} model={result['model_used']} "
          f"fb={result['fallback_count']} latency={result['latency_ms']}ms "
          f"cost=${result['cost_usd']:.2f}")

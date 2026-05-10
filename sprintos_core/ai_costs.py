"""Local-only token and cost estimates for SprintOS AI providers."""

from __future__ import annotations

import math
import os
from typing import Any


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

# Local estimates only. These are intentionally conservative heuristics and are
# not intended to match provider billing exactly.
DEFAULT_PRICE_TABLE = {
    "openai": {
        DEFAULT_OPENAI_MODEL: {"input_cost_per_1m": 0.60, "output_cost_per_1m": 2.40},
    },
    "deepseek": {
        DEFAULT_DEEPSEEK_MODEL: {"input_cost_per_1m": 0.20, "output_cost_per_1m": 0.80},
    },
}


def _env_float(name: str) -> float | None:
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def estimate_tokens_from_chars(text_or_size: Any) -> int:
    if isinstance(text_or_size, (int, float)):
        chars = max(0, int(text_or_size))
    else:
        chars = len(str(text_or_size or ""))
    if chars <= 0:
        return 0
    return int(math.ceil(chars / 4.0))


def estimate_ai_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> dict[str, Any]:
    normalized_provider = str(provider or "offline").strip().lower() or "offline"
    normalized_model = str(model or "").strip()
    safe_input_tokens = max(0, int(input_tokens or 0))
    safe_output_tokens = max(0, int(output_tokens or 0))

    if normalized_provider == "offline":
        return {
            "provider": "offline",
            "model": normalized_model or "offline",
            "input_tokens": safe_input_tokens,
            "output_tokens": safe_output_tokens,
            "estimated_cost_usd": 0.0,
            "warning": "",
            "estimate_label": "Local estimate only; not billing truth.",
        }

    if normalized_provider not in {"openai", "deepseek"}:
        return {
            "provider": normalized_provider or "unknown",
            "model": normalized_model,
            "input_tokens": safe_input_tokens,
            "output_tokens": safe_output_tokens,
            "estimated_cost_usd": None,
            "warning": "No local price estimate configured for this provider.",
            "estimate_label": "Local estimate only; not billing truth.",
        }

    env_prefix = "SPRINTOS_OPENAI" if normalized_provider == "openai" else "SPRINTOS_DEEPSEEK"
    input_override = _env_float(f"{env_prefix}_INPUT_COST_PER_1M")
    output_override = _env_float(f"{env_prefix}_OUTPUT_COST_PER_1M")
    if input_override is not None and output_override is not None:
        input_cost_per_1m = input_override
        output_cost_per_1m = output_override
        warning = "Using local SprintOS env override price estimates."
    else:
        model_prices = (DEFAULT_PRICE_TABLE.get(normalized_provider) or {}).get(normalized_model)
        if not model_prices:
            return {
                "provider": normalized_provider,
                "model": normalized_model,
                "input_tokens": safe_input_tokens,
                "output_tokens": safe_output_tokens,
                "estimated_cost_usd": None,
                "warning": "No local price estimate configured for this provider/model.",
                "estimate_label": "Local estimate only; not billing truth.",
            }
        input_cost_per_1m = float(model_prices["input_cost_per_1m"])
        output_cost_per_1m = float(model_prices["output_cost_per_1m"])
        warning = ""

    estimated_cost_usd = round(
        ((safe_input_tokens * input_cost_per_1m) + (safe_output_tokens * output_cost_per_1m)) / 1_000_000.0,
        8,
    )
    return {
        "provider": normalized_provider,
        "model": normalized_model,
        "input_tokens": safe_input_tokens,
        "output_tokens": safe_output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "warning": warning,
        "estimate_label": "Local estimate only; not billing truth.",
    }

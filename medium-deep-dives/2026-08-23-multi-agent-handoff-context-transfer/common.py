"""Shared scenario + measurement helpers for the handoff experiments.

One scenario is reused across all three frameworks so the numbers compare:

    user: "Order A-1183 arrived damaged. I want a refund."
    triage agent: calls lookup_order("A-1183") -> a chunk of order JSON
    triage agent: hands off to the refund agent
    refund agent: answers

Everything runs on CPU with scripted/fake models. No API keys, no network.
"""

from __future__ import annotations

import json
import os
from typing import Any

import blingfire
from blingfire import load_model, free_model, text_to_ids

# blingfire ships the GPT-2 BPE model inside the wheel; load_model needs its path.
GPT2_MODEL_PATH = os.path.join(os.path.dirname(blingfire.__file__), "gpt2.bin")

USER_REQUEST = "Order A-1183 arrived damaged. I want a refund."

# The tool result is deliberately chunky: this is the part that makes the
# "does the next agent see tool output?" question cost real money.
ORDER_RECORD: dict[str, Any] = {
    "order_id": "A-1183",
    "customer_id": "C-90422",
    "placed_at": "2026-08-02T09:14:00Z",
    "delivered_at": "2026-08-07T16:41:00Z",
    "channel": "web",
    "currency": "USD",
    "total": 248.5,
    "payment": {"method": "card", "last4": "4242", "captured": True},
    "shipping": {
        "carrier": "UPS",
        "tracking": "1Z999AA10123456784",
        "signature": False,
        "address_country": "US",
    },
    "lines": [
        {"sku": "SKU-77", "name": "Ceramic pour-over kettle", "qty": 1, "price": 189.0},
        {"sku": "SKU-12", "name": "Paper filters, 200ct", "qty": 2, "price": 14.75},
        {"sku": "SKU-40", "name": "Scale, 0.1g", "qty": 1, "price": 30.0},
    ],
    "refund_policy": {
        "window_days": 30,
        "damaged_goods_auto_approve_under": 250.0,
        "requires_photo": True,
    },
    "prior_refunds": [],
}

ORDER_JSON = json.dumps(ORDER_RECORD, indent=2)

_TOKENIZER_HANDLE = None


def _tokenizer():
    """GPT-2 BPE shipped inside the blingfire wheel: no network at runtime."""
    global _TOKENIZER_HANDLE
    if _TOKENIZER_HANDLE is None:
        _TOKENIZER_HANDLE = load_model(GPT2_MODEL_PATH)
    return _TOKENIZER_HANDLE


def count_tokens(text: str) -> int:
    """Approximate provider token count with GPT-2 BPE (deterministic, offline).

    `text_to_ids` returns a fixed-width array right-padded with 0, so ask for a
    buffer that cannot overflow (a BPE token is at least one character) and trim
    the trailing padding.
    """
    if not text:
        return 0
    ids = text_to_ids(_tokenizer(), text, len(text) + 8, 0)
    n = len(ids)
    while n > 0 and ids[n - 1] == 0:
        n -= 1
    return n


def release_tokenizer() -> None:
    global _TOKENIZER_HANDLE
    if _TOKENIZER_HANDLE is not None:
        free_model(_TOKENIZER_HANDLE)
        _TOKENIZER_HANDLE = None


# Frameworks stamp fresh UUIDs on messages. They are real bytes on the wire but
# they are not what any of these experiments is measuring, and leaving them in
# makes every run report a different number. Drop them so the counts are stable.
_VOLATILE_KEYS = {"id", "message_id", "response_id", "created_at", "timestamp"}


def strip_volatile(value: Any) -> Any:
    """Recursively remove per-run identifiers from a serialized payload."""
    if isinstance(value, dict):
        return {
            k: strip_volatile(v)
            for k, v in value.items()
            if k not in _VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [strip_volatile(v) for v in value]
    return value


def tokens_of(payload: Any) -> int:
    """Token count of a JSON-serializable request payload."""
    if isinstance(payload, str):
        return count_tokens(payload)
    return count_tokens(
        json.dumps(strip_volatile(payload), ensure_ascii=False, default=str, sort_keys=True)
    )


def rule(title: str, width: int = 74) -> str:
    pad = max(0, width - len(title) - 3)
    return f"-- {title} " + "-" * pad


def preview(text: str, limit: int = 96) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"

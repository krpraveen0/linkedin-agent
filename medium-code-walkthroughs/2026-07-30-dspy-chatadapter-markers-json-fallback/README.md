# DSPy ChatAdapter: text markers by default, JSON fallback on failure

Code for the article **"DSPy Doesn't Send Your LLM a JSON Schema by Default — It Sends Text Markers, Then Silently Retries as JSON"** (2026-07-30).

`dspy_chatadapter_demo.py` uses a fake local LM (no API key, no network) to show:

1. The exact `[[ ## field ## ]]` prompt DSPy's default `ChatAdapter` builds from a `Signature`, including the `reasoning` field injected by `ChainOfThought`.
2. That a well-formed marker reply parses into typed fields in a single LM call.
3. That a marker-free reply makes `ChatAdapter` silently retry the request through `JSONAdapter` — two LM calls to get one answer.

## Setup and run

```bash
python3 -m venv venv && . venv/bin/activate
pip install "dspy==3.2.1"
python3 dspy_chatadapter_demo.py
```

Tested on `dspy==3.2.1` and Python 3.11.

## Real captured output

```
=== SYSTEM MESSAGE DSPy BUILT ===
Your input fields are:
1. `ticket` (str):
Your output fields are:
1. `reasoning` (str):
2. `urgency` (str): one of: low, medium, high
All interactions will be structured in the following way, with the appropriate values filled in.

[[ ## ticket ## ]]
{ticket}

[[ ## reasoning ## ]]
{reasoning}

[[ ## urgency ## ]]
{urgency}

[[ ## completed ## ]]
In adhering to this structure, your objective is:
        Classify a support ticket by urgency.

=== USER MESSAGE DSPy BUILT ===
[[ ## ticket ## ]]
The whole site is down and no one can log in.

Respond with the corresponding output fields, starting with the field `[[ ## reasoning ## ]]`, then `[[ ## urgency ## ]]`, and then ending with the marker for `[[ ## completed ## ]]`.

=== PARSED RESULT (structured) ===
urgency: 'high' | reasoning: 'Site is down for all users.'
LM calls: 1

=== FALLBACK BEHAVIOR ===
urgency: 'high'
call 1: json_mode=False
call 2: json_mode=True
```

## How it was verified

Every claim in the article was checked against the installed `dspy==3.2.1` source, not secondary docs:

- Default adapter: `adapter = settings.adapter or ChatAdapter()` in `dspy/predict/predict.py`.
- Marker pattern: `field_header_pattern = re.compile(r"\[\[ ## (\w+) ## \]\]")` in `dspy/adapters/chat_adapter.py`.
- Fallback: `ChatAdapter.__call__` wraps the marker attempt in `try/except` and retries via `JSONAdapter` unless the error is `ContextWindowExceededError`, it is already a `JSONAdapter`, or `use_json_adapter_fallback` is `False` (which defaults to `True`).

Setting `use_json_adapter_fallback=False` on a `ChatAdapter` and feeding a marker-free reply raises `AdapterParseError` instead of recovering.

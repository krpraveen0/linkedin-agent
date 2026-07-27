# Pydantic AI's Two Retry Budgets — code walkthrough

Companion code for the 2026-07-27 Medium article *"Pydantic AI's Retry Budget Is
Now Two Budgets — and Here's the Exact Message It Sends Your Model When Output
Fails."*

Every script runs with **no API key**. Pydantic AI's built-in `FunctionModel`
stands in for a real model and returns scripted responses, so the messages the
framework constructs (and the retry budgets it enforces) are fully observable.

Verified on `pydantic-ai==2.18.0`, Python 3.11.15. Version 2.18.0 was published
to PyPI on 2026-07-25.

## Setup

```bash
python -m venv venv && . venv/bin/activate
pip install "pydantic-ai==2.18.0"
```

## Run

```bash
python retry_demo.py          # what the framework sends the model on an output failure
python budget_demo.py         # exhaust the OUTPUT budget; read the exception
python tool_budget_demo.py    # the TOOLS budget is a separate, per-tool pool
```

## Captured output (real, from a fresh run)

### `retry_demo.py`

```
FINAL OUTPUT: 'ord-77'
MODEL WAS CALLED: 2 times
RETRY PART SENT BACK -> "'ORD-77' is not lowercase; return the id in lowercase."
part_kind: retry-prompt | tool_name: None
```

The exact string passed to `ModelRetry(...)` reaches the model verbatim as a
`RetryPromptPart`.

### `budget_demo.py`

```
stored output budget: 2
stored tool budget:   1
RAISED: UnexpectedModelBehavior -> Exceeded maximum output retries (2)
```

`retries={'output': 2}` set only the output budget; the tools budget stayed at
its default of `1`.

### `tool_budget_demo.py`

```
stored tool budget: 3 | output budget: 1
RAISED: UnexpectedModelBehavior -> Tool 'lookup' exceeded max retries count of 3. Consider raising the retry limit, or see the docs on tool retries: https://ai.pydantic.dev/tools-advanced/#tool-retries
tool actually executed: 4 times (1 initial + 3 retries)
```

The tool ran four times (initial call + three retries) and the exception names
the tool. The output budget was never touched.

## Diagrams

- `fig1-retry-loop.svg` — how a validation failure becomes another model turn.
- `fig2-two-budgets.svg` — the independent `tools` and `output` pools.

## Note

This walkthrough validates the retry mechanics and message shapes against a real
run of `pydantic-ai==2.18.0`. The library ships near-daily releases, so re-check
the version you install.

# OpenTelemetry GenAI agent spans — code walkthrough

Companion code for the article *"OpenTelemetry Moved Its GenAI Conventions Into
Their Own Repo. Here's How to Trace an Agent With Them."* (`article.md` in this
folder).

Two small, fully offline, deterministic scripts that use the **real** GenAI
convention constants shipped in `opentelemetry-semantic-conventions`. No LLM, no
network, no API key.

## Files

- `agent_tracing.py` — a tiny LLM-free "unit converter" agent instrumented with
  OpenTelemetry using the GenAI attribute constants. Emits an `invoke_agent`
  root span with two nested `execute_tool` spans and prints the span tree from
  an in-memory exporter (timestamps omitted so output is reproducible).
- `inspect_semconv.py` — inspects the installed `gen_ai_attributes` module and
  reports how many `gen_ai.*` constants were flagged as moved to the dedicated
  `semantic-conventions-genai` repo, plus the `gen_ai.system` →
  `gen_ai.provider.name` migration.
- `article.md` — the full article.
- `fig1-span-tree.svg`, `fig2-move.svg` — the diagrams.

## Setup & run

```bash
python3 -m venv venv
./venv/bin/pip install opentelemetry-sdk opentelemetry-semantic-conventions
./venv/bin/python agent_tracing.py
./venv/bin/python inspect_semconv.py
```

Verified on **opentelemetry-sdk 1.44.0**, **opentelemetry-semantic-conventions
0.65b0** (released July 16, 2026), and **Python 3.11.15**.

## Real captured output

`agent_tracing.py`:

```
agent results: [37.0, 26.1]
span tree (root -> children):
- invoke_agent unit-converter   [invoke_agent]
  - execute_tool to_celsius   [execute_tool]
      gen_ai.tool.name = to_celsius
      gen_ai.tool.call.arguments = 98.6
      gen_ai.tool.call.result = 37.0
  - execute_tool to_miles   [execute_tool]
      gen_ai.tool.name = to_miles
      gen_ai.tool.call.arguments = 42.0
      gen_ai.tool.call.result = 26.1
```

`inspect_semconv.py`:

```
opentelemetry-semantic-conventions: 0.65b0
gen_ai.* string constants in module: 60
...carrying a 'moved to semantic-conventions-genai' deprecation note: 60

gen_ai.system -> Deprecated: Replaced by `gen_ai.provider.name`, which has moved to the [OpenTelemetry GenAI semantic conventions repository](https://github.com/open-telemetry/semantic-conventions-genai).

Agent operation names still importable (values unchanged):
  CREATE_AGENT = 'create_agent'
  INVOKE_AGENT = 'invoke_agent'
  EXECUTE_TOOL = 'execute_tool'
```

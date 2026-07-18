# OpenTelemetry Moved Its GenAI Conventions Into Their Own Repo. Here's How to Trace an Agent With Them.

If you upgraded `opentelemetry-semantic-conventions` this week and your editor
lit up with deprecation warnings on every `gen_ai.*` constant you import, that
was not a mistake. On July 16, 2026 the Python package published version
[`0.65b0`](https://pypi.org/project/opentelemetry-semantic-conventions/), and in
that release the entire GenAI namespace inside the core package was marked
deprecated and pointed at a brand-new home: the
[`open-telemetry/semantic-conventions-genai`](https://github.com/open-telemetry/semantic-conventions-genai)
repository.

That sounds like bookkeeping. It is actually the moment the conventions for
tracing AI agents — the span names, the attribute keys, the operation
vocabulary — got their own governance and their own release cadence, separate
from the rest of OpenTelemetry. If you are adding observability to an agent in
2026, these are the names your spans should use. This article verifies exactly
what those names are against the installed package (not a blog post), then wires
them onto a small agent and prints the resulting span tree.

## What changed on July 16

The GenAI semantic conventions have lived under
`opentelemetry.semconv._incubating.attributes.gen_ai_attributes` for a while.
They are still importable there — the constants and their string values did not
change — but every one of them now carries the same docstring: *moved to the
OpenTelemetry GenAI semantic conventions repository.* The old
`docs/gen-ai/gen-ai-agent-spans.md` path in the main
[`semantic-conventions`](https://github.com/open-telemetry/semantic-conventions)
repo now returns a one-line notice that the content has relocated.

Two consequences matter for a developer:

1. The canonical definition of an agent span lives in the new repo, and it is
   still marked **Development** (not stable). Names can change; pin your
   dependency and read the changelog.
2. `gen_ai.system` — the attribute a lot of existing instrumentation sets to
   identify the model provider — is being replaced by `gen_ai.provider.name`.
   The package says so directly, which we will confirm below.

## The agent span vocabulary

The conventions define operations through a single required attribute,
`gen_ai.operation.name`, whose well-known values in the installed package are
`create_agent`, `invoke_agent`, `execute_tool`, `invoke_workflow`, `chat`,
`generate_content`, `text_completion`, `embeddings`, and `retrieval`. The span
name is derived from the operation, per the
[agent spans spec](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md):

- `create_agent {gen_ai.agent.name}` — building or configuring an agent.
- `invoke_agent {gen_ai.agent.name}` — one run of the agent (falls back to just
  `invoke_agent` when the name is not available).
- `execute_tool {gen_ai.tool.name}` — one tool call, defined in the
  [general spans doc](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md).
- `chat {gen_ai.request.model}` — a single model call inside the run.

On the agent spans, `gen_ai.operation.name` and `gen_ai.provider.name` are
**Required**; the agent name, id, version, and model are conditionally required
"if provided by the application." On an `execute_tool` span, `gen_ai.tool.name`
is **Required**. There is also a required duration metric,
`gen_ai.client.operation.duration`, and a recommended token metric,
`gen_ai.client.token.usage`.

The shape that falls out of this is a tree: an `invoke_agent` span at the root,
with `chat` spans for each model call and `execute_tool` spans for each tool
call nested underneath. That nesting is the whole point — it is what lets a
backend answer "which tool call inside which agent run blew the latency budget."

The spec is also explicit about one detail that trips up naive instrumentation:
`gen_ai.agent.name`, `gen_ai.operation.name`, and `gen_ai.request.model` should
be set **at span creation time**, not patched on at the end, because a sampler
decides whether to keep a span before the run finishes. If you attach the agent
name only after the agent returns, a head sampler never sees it. One more
operation in the packaged enum is worth knowing:
`invoke_workflow {gen_ai.workflow.name}` for a non-agent-driven orchestration —
useful when your "agent" is really a fixed graph and you want the traces to say
so. The spec repo also documents a `plan` span, but its operation value has not
yet landed in the packaged `0.65b0` enum — a concrete reminder that these
conventions are still Development-status and the docs can run ahead of the
release you install.

## Try It Yourself

Two short scripts, both fully offline. No LLM, no API key, no network — the
attribute names and span structure are what we are demonstrating, so a plain
Python "unit converter" agent stands in for a model-driven one and keeps the
output reproducible.

Set up the environment:

```bash
python3 -m venv venv
./venv/bin/pip install opentelemetry-sdk opentelemetry-semantic-conventions
```

This pulls in `opentelemetry-sdk` 1.44.0 and
`opentelemetry-semantic-conventions` 0.65b0 (the July 16 release), on Python
3.11.

### 1. Wire the GenAI attributes onto real spans

The agent runs two tools. Each tool call gets an `execute_tool` span nested
under a single `invoke_agent` span, and every attribute key comes straight from
the installed convention constants — no hand-typed strings.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_OPERATION_NAME, GEN_AI_PROVIDER_NAME, GEN_AI_AGENT_NAME,
    GEN_AI_TOOL_NAME, GEN_AI_TOOL_CALL_ARGUMENTS, GEN_AI_TOOL_CALL_RESULT,
    GenAiOperationNameValues,
)

def run_tool(name, arg):
    with tracer.start_as_current_span(f"execute_tool {name}") as span:
        span.set_attribute(GEN_AI_OPERATION_NAME, GenAiOperationNameValues.EXECUTE_TOOL.value)
        span.set_attribute(GEN_AI_TOOL_NAME, name)
        span.set_attribute(GEN_AI_TOOL_CALL_ARGUMENTS, str(arg))
        result = TOOLS[name](arg)
        span.set_attribute(GEN_AI_TOOL_CALL_RESULT, str(result))
        return result
```

An `InMemorySpanExporter` captures the finished spans so we can render the tree
ourselves (the full script is in the companion repo). Running it prints:

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

That is the canonical agent trace shape, produced with the real constants: one
`invoke_agent` root, two `execute_tool` children, each tagged with the required
`gen_ai.tool.name` plus the tool arguments and result.

### 2. Verify the migration against the package, not a blog

The more useful check is empirical: how much of the `gen_ai.*` namespace did the
July 16 release actually flag as moved? This script reads the module's own
source and counts.

```python
import inspect
from importlib.metadata import version
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as g

src = inspect.getsource(g)
constants = [n for n in dir(g) if n.startswith("GEN_AI_") and n.isupper()]
moved = [n for n in constants
         if "semantic-conventions-genai" in src.split(f"{n}: Final", 1)[1][:400]]
print(f"gen_ai.* string constants in module: {len(constants)}")
print(f"...carrying a 'moved' deprecation note: {len(moved)}")
```

Output:

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

All 60 `gen_ai.*` string constants in the module are flagged as relocated — this
is a wholesale move, not a partial one. The `gen_ai.system` docstring names its
replacement in plain text. And the operation-name enum still resolves to
`create_agent` / `invoke_agent` / `execute_tool`, so the migration is a change of
home and of the provider attribute, not a rename of the operations themselves.

## What this means for your instrumentation

If you already emit GenAI spans, the practical to-do list is short. Keep using
`invoke_agent`, `execute_tool`, and friends — those values are stable across the
move. Swap `gen_ai.system` for `gen_ai.provider.name` when you set the provider.
And treat the whole namespace as **Development**: the conventions now have a
dedicated repository precisely so they can iterate, which means a minor version
bump can still move a key. Pin `opentelemetry-semantic-conventions`, import the
constants instead of hardcoding strings (so a rename surfaces as an import
error, not a silently wrong attribute), and watch the new repo's releases rather
than the core one.

The upside of the split is real: agent tracing is now a first-class,
independently versioned surface in OpenTelemetry, with a documented span
vocabulary you can adopt today without waiting for vendor-specific formats to
converge.

## Key Takeaways

- `opentelemetry-semantic-conventions` **0.65b0** (July 16, 2026) marks the
  entire `gen_ai.*` namespace deprecated and relocated to the dedicated
  [`semantic-conventions-genai`](https://github.com/open-telemetry/semantic-conventions-genai)
  repo — verified: all 60 constants in the installed module carry the note.
- Agent spans follow fixed names: `invoke_agent {agent.name}`,
  `execute_tool {tool.name}`, `create_agent {agent.name}`, with
  `gen_ai.operation.name` and `gen_ai.provider.name` required.
- `gen_ai.system` is replaced by `gen_ai.provider.name`; the operation-name
  values (`invoke_agent`, `execute_tool`, `create_agent`) are unchanged.
- The conventions are still **Development** status — import the constants, pin
  the version, and track the new repository.

**Sources:** [opentelemetry-semantic-conventions on PyPI](https://pypi.org/project/opentelemetry-semantic-conventions/) · [OpenTelemetry GenAI semantic conventions repo](https://github.com/open-telemetry/semantic-conventions-genai) · [GenAI agent spans spec](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) · [GenAI spans (execute tool) spec](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md) · [OpenTelemetry Semantic Conventions site (1.43.0)](https://opentelemetry.io/docs/specs/semconv/) · installed package inspection, `opentelemetry-semantic-conventions==0.65b0`, Python 3.11.15.

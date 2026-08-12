# create_agent + a raw `response_format` schema (LangChain 1.x)

Code for the 2026-08-12 article *"I Gave create_agent a Response Schema. For My
Local Model, LangChain Turned It Into a Tool."*

`demo.py` shows, with **no API key and no network**, how LangChain 1.0's
`create_agent` decides between `ProviderStrategy` (native structured output) and
`ToolStrategy` (a synthetic tool built from your schema) when you pass a raw
Pydantic model as `response_format`. A scripted `BaseChatModel` stands in for a
real LLM and records which tools it is offered.

## Setup

```bash
python3 -m venv venv
. venv/bin/activate
pip install "langchain>=1.0"
```

Verified versions:

```
langchain 1.3.15
langchain-core 1.5.4
langgraph 1.2.11
```

## Run

```bash
python demo.py
```

## Real captured output

```text
== Demo 1: ToolStrategy turns your schema into a tool ==
  injected tool name: Weather
  injected tool args: ['city', 'temp_c', 'summary']

== Demo 2: local model (no native structured output) ==
  tools the model was offered: ['get_weather', 'Weather']
  structured_response: city='Paris' temp_c=19.0 summary='clear'

== Demo 3: model whose profile advertises structured_output ==
  tools the model was offered: ['get_weather']
  structured_response: city='Paris' temp_c=19.0 summary='clear'
```

## What to notice

- **Demo 1** — `ToolStrategy(schema=Weather)` builds a tool named `Weather`
  whose arguments are your schema's fields.
- **Demo 2** — a local-style model (`profile=None`, name not on LangChain's
  hardcoded `FALLBACK_MODELS_WITH_STRUCTURED_OUTPUT` list) is offered
  `['get_weather', 'Weather']`. Your real tool and the synthetic schema-tool
  compete in the same list.
- **Demo 3** — the same agent with a model whose `profile` advertises
  `structured_output` is offered only `['get_weather']`; the schema is handled
  by provider-native structured output (`ProviderStrategy`).

The selection logic lives in `_supports_provider_strategy` in
[`langchain/agents/factory.py`](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/factory.py).

## Files

- `demo.py` — the runnable example
- `article.md` — the full article
- `figure-1-strategy-resolution.svg` — strategy resolution flow
- `figure-2-offered-tools.svg` — offered tool lists, local vs capable model

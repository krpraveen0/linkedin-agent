# Pydantic AI v2 "Capability" primitive — code walkthrough

Companion code for the article *"Pydantic AI v2 Turned Every Agent Extension
Point Into One Object. Here's What a 'Capability' Actually Does."*
(`article.md` in this folder).

Two small, fully offline, deterministic scripts demonstrate that in Pydantic
AI v2, tools, instructions, and lifecycle hooks are all the same kind of
object — a **capability** — that you compose into an agent through a single
`capabilities=[...]` list. No API key required: the model is driven with
Pydantic AI's built-in `FunctionModel` / `TestModel`.

## Files

- `capability_agent.py` — composes an agent from a `Toolset` capability (a tool
  bundled with its instructions) and a `Hooks` capability (a request counter),
  and prints what each capability delivered.
- `capability_reuse.py` — shows one capability object plugged into two
  independent agents, sharing state.
- `article.md` — the full article.
- `diagram1_composition.svg`, `diagram2_reuse.svg` — the diagrams.

## Setup & run

```bash
python3 -m venv venv
./venv/bin/pip install pydantic-ai
./venv/bin/python capability_agent.py
./venv/bin/python capability_reuse.py
```

Verified on **pydantic-ai 2.9.1**, **Python 3.11.15**.

## Real captured output

`capability_agent.py`:

```
instructions seen by model : 'If asked how long some text is, call word_count.'
tools seen by model        : ['word_count']
final output               : The text has 3 words.
model requests (via hook)  : 2
```

`capability_reuse.py`:

```
translator output: bonjour
summarizer output: tl;dr
total model requests counted by the one shared capability: 2
```

The output above was captured directly from running the scripts and is
reproduced verbatim in the article. An independent re-run in a fresh virtualenv
produced byte-identical output.

## Note on the duplicate-id constraint

Capability `id`s must be unique within a single run. Supplying the same
capability both at construction and as a per-run argument raises:

```
pydantic_ai.exceptions.UserError: Capability id 'audit' is used by multiple
capabilities. Capability ids must be unique within a run.
```

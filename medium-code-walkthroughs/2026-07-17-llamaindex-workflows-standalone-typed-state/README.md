# LlamaIndex Workflows standalone package — code walkthrough

Companion code for the article *"LlamaIndex Workflows Is Now a Standalone
Package. Its Typed State Is What Makes That Matter."* (`article.md` in this
folder).

Two small, fully offline, deterministic scripts on the standalone `workflows`
package (installed via `pip install llama-index-workflows`, imported as
`workflows`). No LLM, no network, no API key — the length-based score stands in
for a model call so the engine's behaviour is reproducible for fact-checking.

## Files

- `triage.py` — a workflow with typed Pydantic state, event branching
  (`ScoredEvent | RetryEvent`), a bounded retry loop, and live event streaming.
- `resume.py` — freezes the run's `Context` to JSON via `to_dict()` and rebuilds
  it with `from_dict()`, reading the typed state back without rerunning a step.
- `article.md` — the full article.
- `fig1-event-flow.svg`, `fig2-state-freeze.svg` — the diagrams.

## Setup & run

```bash
python3 -m venv venv
./venv/bin/pip install llama-index-workflows pydantic
./venv/bin/python triage.py
./venv/bin/python resume.py
```

Verified on **llama-index-workflows 2.22.2** (imports as `workflows`) and
**Python 3.11.15**. In a clean install with only `llama-index-workflows` +
`pydantic`, `import llama_index.core` raises `ModuleNotFoundError` — the engine
no longer pulls in the rest of LlamaIndex.

## Real captured output

`triage.py`:

```
[stream] scoring attempt #1
[stream] transient miss -> looping back
[stream] scoring attempt #2
final verdict: escalate
state.attempts: 2
state.decisions: ['escalate']
```

`resume.py`:

```
frozen JSON size (bytes): 737
restored attempts: 2
restored decisions: ['escalate']
```

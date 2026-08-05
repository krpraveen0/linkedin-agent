# Haystack 3.0 loop guards — code walkthrough

Companion code for the article **"Haystack 3.0 Gives You Two Ways to Loop an Agent. One Crashes When It Runs Away; the Other Just Stops and Hands You a Half-Finished Answer."**

Three self-contained scripts prove, with **no model, no API key, and no network at runtime**, that Haystack 3.0's two looping constructs guard against runaway loops in opposite ways:

- a `Pipeline` cycle that never exits **raises `PipelineMaxComponentRuns`** (the run dies),
- an `Agent` whose exit condition is never met **logs a warning and returns a partial result** (no exception),
- and both guards default to **100**.

Verified against `haystack-ai==3.0.0` (released 2026-07-20), Python 3.11.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install "haystack-ai==3.0.0"
```

## Run

### 1. Pipeline loop crashes — `PipelineMaxComponentRuns`

```bash
./.venv/bin/python demo1_pipeline_crashes.py
```

Real captured output:

```
RAISED PipelineMaxComponentRuns: Maximum run count 3 reached for component 'loop'
Worker.run executed 3 times; values seen: [0, 1, 2]
```

With `max_runs_per_component=3`, the worker runs exactly 3 times (visits 0, 1, 2). The 4th scheduling finds `visits >= 3` and raises.

### 2. Agent loop stops quietly — warning, then a partial result

```bash
./.venv/bin/python demo2_agent_stops_quietly.py
```

Real captured output:

```
WARNING haystack.components.agents.agent: Agent reached maximum agent steps of 5, stopping.
RETURNED NORMALLY (no exception raised)
step_count:       5
messages collected: 11
tool_call_counts: {'noop': 5}
```

The stub chat generator always requests a tool call and never returns plain text, so the default `"text"` exit condition is never met. The Agent runs its 5 steps, logs one warning, and returns normally with `step_count == max_agent_steps`.

### 3. Both defaults are 100 — straight from the installed package

```bash
./.venv/bin/python demo3_defaults_from_package.py
```

Real captured output:

```
haystack-ai version: 3.0.0
Pipeline.max_runs_per_component default: 100
Agent.max_agent_steps default:           100
same default value? True
```

## Governing facts (direct package inspection)

- `haystack/core/pipeline/base.py` — `max_runs_per_component: int = 100`; the scheduler raises `PipelineMaxComponentRuns` when `comp["visits"] >= self._max_runs_per_component`, checked before the component runs.
- `haystack/core/errors.py` — `class PipelineMaxComponentRuns(PipelineError)`.
- `haystack/components/agents/agent.py` — `max_agent_steps: int = 100`; the loop `while counter < max_agent_steps` breaks out and calls `logger.warning("Agent reached maximum agent steps of {max_agent_steps}, stopping.")`, then returns the result. No exception path.

## Files

- `demo1_pipeline_crashes.py` — a `Pipeline` cycle that raises `PipelineMaxComponentRuns`
- `demo2_agent_stops_quietly.py` — an `Agent` that hits `max_agent_steps` and returns a partial result
- `demo3_defaults_from_package.py` — prints both guard defaults from the installed package
- `article.md` — the full article
- `fig1_two_guards.svg`, `fig2_run_count_boundary.svg` — diagrams

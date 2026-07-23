# Google ADK LoopAgent: What Actually Stops the Loop

Runnable code for the Medium article *"Google ADK's LoopAgent Only Stops on One
Signal — and ADK 2.0 Is Already Replacing It"* (2026-07-23).

All three scripts run locally, CPU-only, **with no LLM and no API key** — a custom
`BaseAgent` yields hand-built events, exercising the exact loop engine an
LLM-backed agent would use.

## Environment

- Python 3.11.15
- `google-adk` **2.5.0**

## Setup

```bash
pip install google-adk
```

If `pip` fails to uninstall a system-managed PyYAML, use
`pip install --ignore-installed PyYAML google-adk`.

## Run

```bash
python 01_completion_is_not_stop.py
python 02_escalate_stops.py
python 03_deprecation.py
```

## What each file shows

### `01_completion_is_not_stop.py` — finishing a turn does not stop the loop

A `Worker` reports "pass N done" and returns every iteration. It never escalates,
so the loop runs the full `max_iterations=3`.

Real captured output:

```text
[worker] pass 1 done
[worker] pass 2 done
[worker] pass 3 done

Worker turns executed: 3  (max_iterations was 3)
```

### `02_escalate_stops.py` — `escalate=True` is the only early exit

A `Critic` sets `EventActions(escalate=True)` once its quality gate passes on pass
2. With `max_iterations=10`, the loop stops at 2.

Real captured output:

```text
[critic] pass 1: revise
[critic] pass 2: APPROVED -> escalate

Critic turns executed: 2  (max_iterations was 10)
```

### `03_deprecation.py` — the ADK 2.0 deprecation notice

Constructing a `LoopAgent` in 2.5.0 emits a `DeprecationWarning` pointing at the
new graph-based `Workflow` runtime (ADK 2.0 GA 2026-05-19).

Real captured output:

```text
LoopAgent is deprecated in favor of Workflow and will be removed in a future version. Workflow cannot yet be used as an LlmAgent sub-agent.
```

## Diagrams

- `figure1_loop_control.svg` — the loop's continue/stop decision flow.
- `figure2_two_runs.svg` — the two runs side by side.

## Sources

- ADK loop-agents docs: https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/
- adk-python CHANGELOG (2.0.0, 2026-05-19): https://github.com/google/adk-python/blob/main/CHANGELOG.md
- loop_agent.py source: https://github.com/google/adk-python/blob/main/src/google/adk/agents/loop_agent.py
- google-adk on PyPI: https://pypi.org/project/google-adk/

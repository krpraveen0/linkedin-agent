# LangGraph `durability` modes and resume-replay — working walkthrough

Companion code for the Medium article "LangGraph Checkpoints Your Agent at Every Superstep — But a
Crash Still Re-Runs the Node That Failed" (2026-07-24).

All three scripts were executed against `langgraph==1.2.9` (released 2026-07-10),
`langgraph-checkpoint==4.1.1`, and `langgraph-checkpoint-sqlite==3.1.0` in a clean virtualenv.
Every output block below is copied verbatim from a real run — nothing was invented or cleaned up.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "langgraph==1.2.9" langgraph-checkpoint-sqlite
```

## What the `durability` parameter is

Read it straight out of the installed package:

```bash
python3 - <<'PY'
import inspect
from typing import get_args
from langgraph.types import Durability
from langgraph.pregel import Pregel
params = inspect.signature(Pregel.invoke).parameters
print("modes:", get_args(Durability))
print("durability is a param:", "durability" in params)
print("signature default:", params["durability"].default)
PY
```

Real output:

```
modes: ('sync', 'async', 'exit')
durability is a param: True
signature default: None
```

The signature default is the sentinel `None`, which resolves to the documented default `"async"`.

## `durability_kill.py` — what survives an ungraceful crash

A 3-node graph (A → B → C) runs against a file-backed SQLite checkpointer. Node B calls
`os._exit(137)` to simulate an OOM/SIGKILL (no exception handling runs). The driver then reopens the
same database and reports what survived, for `sync` vs `exit`.

```bash
python3 durability_kill.py
```

Real output:

```
=== durability='sync' : worker runs, then is hard-killed in node B ===
  worker: node A completed a superstep
  worker: node B is about to be hard-killed (os._exit)
  worker exit code: 137
  state persisted after hard kill: ['A']
  next node(s) a resume would run: ('B',)

=== durability='exit' : worker runs, then is hard-killed in node B ===
  worker: node A completed a superstep
  worker: node B is about to be hard-killed (os._exit)
  worker exit code: 137
  state persisted after hard kill: None
  next node(s) a resume would run: (none / restart)
```

`sync` flushes each completed superstep before the next starts, so node A's result survives and a
resume picks up at B. `exit` writes only on a clean exit, which never happened, so nothing survives
and a resume restarts the whole graph.

(`durability_worker.py` is the child process that `durability_kill.py` launches.)

## `durability_replay.py` — resume re-runs the failed node

A → B → C with an in-memory checkpointer. Node C crashes on its first execution and succeeds on the
retry. Each node counts its executions.

```bash
python3 durability_replay.py
```

Real output:

```
=== durability='sync' ===
  SIDE EFFECT: node A ran (call #1)
  SIDE EFFECT: node B ran (call #1)
  SIDE EFFECT: node C ran (call #1)
  -> crashed: node C crashed mid-run (simulated outage)
  persisted log after crash: ['A', 'B']
  next node(s) to run on resume: ('C',)
  SIDE EFFECT: node C ran (call #2)
  final log: ['A', 'B', 'C']
  total node executions: {'A': 1, 'B': 1, 'C': 2}

=== durability='exit' ===
  SIDE EFFECT: node A ran (call #1)
  SIDE EFFECT: node B ran (call #1)
  SIDE EFFECT: node C ran (call #1)
  -> crashed: node C crashed mid-run (simulated outage)
  persisted log after crash: ['A', 'B']
  next node(s) to run on resume: ('C',)
  SIDE EFFECT: node C ran (call #2)
  final log: ['A', 'B', 'C']
  total node executions: {'A': 1, 'B': 1, 'C': 2}
```

A and B run once (their supersteps were checkpointed and skipped on resume). Node C runs **twice**:
the checkpoint boundary sits before C, so C has no partial-progress record and re-executes from the
top. Any side effect C performed before crashing repeats. This is independent of the durability mode.

## Files

- `durability_replay.py` — node-replay-on-resume demo (in-memory checkpointer)
- `durability_kill.py` — sync vs exit under a hard kill (file-backed checkpointer); spawns the worker
- `durability_worker.py` — child process that hard-kills itself in node B
- `article.md` — the full article
- `fig1-durability-modes.svg`, `fig2-resume-replay.svg` — diagrams

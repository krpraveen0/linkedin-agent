# LangGraph Checkpoints Your Agent at Every Superstep — But a Crash Still Re-Runs the Node That Failed

"Durable execution" is the phrase every agent framework reaches for in 2026. The pitch is comforting: your agent saves its progress as it runs, so a timeout, a restart, or a human approval pause doesn't throw away hours of work. LangGraph's persistence layer is one of the more mature implementations of that idea, and the [official docs](https://docs.langchain.com/oss/python/langgraph/durable-execution) describe it plainly — the graph checkpoints its state as it goes, and you resume from the last checkpoint instead of rerunning everything.

That promise is real, but it hides two behaviors that decide whether your production agent actually recovers or quietly does the wrong thing. The first is a single setting most people never touch: `durability`. The second is what happens to the node that was running when the process died. I installed `langgraph==1.2.9` (released [2026-07-10](https://github.com/langchain-ai/langgraph/releases)), inspected the real API, and ran two crash scenarios to see exactly what survives and what repeats. The results line up with the docs, and they are worth internalizing before you ship a side-effectful agent.

This distinction has become a live argument. A [2026 Diagrid post](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) makes the case that checkpoint-based persistence in LangGraph, CrewAI, and Google ADK is not the same guarantee as the durable execution you get from a workflow engine. Testing the actual behavior is the fastest way to see who's right about what.

## The `durability` knob nobody sets

LangGraph writes a checkpoint at the end of each *superstep* — one tick of the graph in which every ready node runs. What the `durability` setting controls is *when* that write is flushed relative to the next superstep starting. It is a parameter on `invoke`, `stream`, and their async twins, and its type is a plain three-value literal. You can read it straight out of the installed package:

```python
import inspect
from typing import get_args
from langgraph.types import Durability
from langgraph.pregel import Pregel

params = inspect.signature(Pregel.invoke).parameters
print("modes:", get_args(Durability))
print("durability is a param:", "durability" in params)
print("signature default:", params["durability"].default)
```

Running that against 1.2.9 prints:

```
modes: ('sync', 'async', 'exit')
durability is a param: True
signature default: None
```

The signature default is the sentinel `None`, which LangGraph resolves to the documented default of `"async"` (the docstring on `invoke` reads "defaults to `async`"). The three modes, per the [docs](https://docs.langchain.com/oss/python/langgraph/durable-execution):

- **`"sync"`** — changes are persisted synchronously *before* the next step starts.
- **`"async"`** — the default; changes are persisted asynchronously *while* the next step executes. Fast, but there is a small window where a crash mid-step means the checkpoint never lands.
- **`"exit"`** — changes are persisted only when the graph exits (success, error, or interrupt). Best throughput for long graphs, but intermediate state is never saved, so you cannot recover from a mid-run process crash.

Most tutorials show a checkpointer and stop there, leaving you on `async`. That is a reasonable default, but it is a *durability-versus-throughput* choice, and the difference only shows up on the day something dies unexpectedly.

## What actually survives a crash

To see the modes diverge, I need a crash that runs no cleanup — an out-of-memory kill or a `SIGKILL`, not a caught Python exception. So the worker graph runs three sequential nodes and node B calls `os._exit(137)`, which terminates the process immediately with no exception handling. A driver runs that worker for each mode against a *file-backed* SQLite checkpointer, then reopens the same database to ask what survived.

```python
def node_a(state):
    print("  worker: node A completed a superstep")
    return {"log": ["A"]}

def node_b(state):
    print("  worker: node B is about to be hard-killed (os._exit)")
    os._exit(137)  # ungraceful: mimics SIGKILL/OOM, no exception handling runs

# ...compile A -> B -> C with a SqliteSaver, then:
app.invoke({"log": []}, {"configurable": {"thread_id": tid}}, durability=durability)
```

The real output, byte for byte:

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

There is the whole argument in eight lines. Under `sync`, node A's completed work was flushed before B started, so after the kill the checkpoint still holds `['A']` and a resume picks up at B. Under `exit`, nothing was written until the graph cleanly exited, which it never did, so the checkpoint is empty and a resume has no choice but to start the entire graph over, re-running A and its side effects from scratch. Same graph, same crash, opposite recovery story, decided by one keyword argument.

## Resume re-runs the failed node

Now the subtler behavior, and the one that bites even when your durability setting is correct. When you resume, LangGraph does not continue from the line inside the node where it crashed. It re-executes the *entire* node. The docs are explicit about the consequence: resuming starts at the beginning of the node where execution stopped, so you should wrap non-deterministic or side-effectful operations to keep them from being repeated on resume.

To watch that happen, I gave each node a call counter and made node C crash on its first execution, then succeed on its retry:

```python
def node_c(state):
    CALLS["C"] += 1
    print("  SIDE EFFECT: node C ran (call #%d)" % CALLS["C"])
    if C_SHOULD_CRASH and CALLS["C"] == 1:
        raise RuntimeError("node C crashed mid-run (simulated outage)")
    return {"log": ["C"]}
```

Running A → B → C with an in-memory checkpointer, crashing at C, then resuming:

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
```

A and B each ran once; resume correctly skipped the supersteps that had already been checkpointed. But **node C ran twice**: once for the crash, once for the recovery. The checkpoint that let A and B be skipped exists at the superstep boundary *before* C, so C has no partial-progress record to resume from. Everything C did before it raised (the print here, but a payment charge, an email, or an `INSERT` in real code) happens again on the second execution.

This is at-least-once execution at the node level, and it is exactly the gap the [Diagrid critique](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) points at: checkpointing between supersteps is not the same as durable execution that records progress *within* a step. Neither `sync` nor `exit` changes it, because it is about checkpoint granularity, not flush timing.

## Try It Yourself

Everything above runs on CPU with no model API key. Two small scripts, a fresh virtualenv:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "langgraph==1.2.9" langgraph-checkpoint-sqlite
python3 durability_kill.py     # sync vs exit under a hard kill
python3 durability_replay.py   # the crashed node runs twice
```

The full `durability_kill.py`, `durability_worker.py`, and `durability_replay.py` are in the companion repository linked under Sources. The output blocks above are copied verbatim from these runs against `langgraph==1.2.9`, `langgraph-checkpoint==4.1.1`, and `langgraph-checkpoint-sqlite==3.1.0` — nothing was cleaned up or invented. If your versions differ, re-run and compare; the point is to trust the behavior you observe, not the paragraph describing it.

## What this means for your agent

Two rules fall out of the runs.

First, treat `durability` as a deliberate choice, not a default you inherited. If a graph does real work between nodes (external writes, spend, anything you cannot cheaply redo), `async` leaves a crash window and `exit` gives up intermediate recovery entirely. Move those graphs to `sync` and pay the synchronous-write latency for the ability to resume. Save `exit` for short, cheap, or fully idempotent graphs where restarting from zero costs nothing.

Second, make every side-effectful node idempotent, because resume will run it again from the top. LangGraph's own guidance is to push non-deterministic and side-effecting operations into cached units of work so their results are replayed from persistence rather than recomputed. In practice that means an idempotency key on the charge, an upsert instead of an insert, or a check-before-send guard — so the second execution is a no-op. No durability mode removes this requirement; it is a property your node code has to provide.

Durable execution in LangGraph is genuinely useful, but it is durable at the granularity of a superstep, with a flush policy you control and a replay policy you don't. Knowing where those two lines sit is the difference between an agent that recovers cleanly and one that double-charges a customer the first time a pod restarts.

## Key Takeaways

- LangGraph's `durability` parameter (`Literal["sync", "async", "exit"]`, default `"async"`) controls *when* checkpoints are flushed; it is verifiable directly from `langgraph==1.2.9`.
- Under an ungraceful crash, `sync` preserved completed work (`['A']`, resume from B) while `exit` preserved nothing (full restart) — confirmed by a hard-kill run.
- Resume re-executes the entire failed node, not the line after the failure: in the test, the crashed node C ran twice, so any pre-crash side effect repeats.
- Checkpointing happens at superstep boundaries, so this at-least-once node behavior is independent of the durability mode you choose.
- Pick `sync` for side-effectful graphs, reserve `exit` for cheap or idempotent ones, and make every side-effecting node idempotent regardless.

## Sources

- LangGraph durable execution documentation — https://docs.langchain.com/oss/python/langgraph/durable-execution (accessed 2026-07-24)
- `Durability` type reference, LangChain — https://reference.langchain.com/python/langgraph/types/Durability
- LangGraph releases (1.2.9, 2026-07-10) — https://github.com/langchain-ai/langgraph/releases
- "Why Checkpoints Aren't Durable Execution," Diagrid, 2026 — https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows
- Direct inspection of installed packages: `langgraph==1.2.9`, `langgraph-checkpoint==4.1.1`, `langgraph-checkpoint-sqlite==3.1.0`
- Companion runnable code (auto-generated by the daily-medium-article cloud routine): PR link below

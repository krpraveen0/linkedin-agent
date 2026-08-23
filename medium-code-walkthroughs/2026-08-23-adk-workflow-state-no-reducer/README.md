# ADK 2.0 Workflow Runtime: no state reducer on fan-in

Companion code for the Medium article *"I Fanned Out Two ADK 2.0 Nodes to the
Same State Key. One Silently Won — No Reducer, No Error."* (2026-08-23).

Two runnable scripts, both fully offline — **no model, no API key, no network**:

- `adk_fan_in_state.py` — a Google ADK 2.0 `Workflow` that fans out to two
  parallel `FunctionNode`s. Part A has both write the same `state` key (a
  collision). Part B shows the fix: branch-private keys plus a `JoinNode`.
- `langgraph_contrast.py` — the same fan-out pattern in LangGraph, which
  refuses it at runtime.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "google-adk==2.7.1" "langgraph==1.2.11"
```

Tested with `google-adk` 2.7.1 (ADK 2.0 line, GA 2026-05-19) and `langgraph`
1.2.11 on Python 3.11.

## Run the ADK demo

```bash
python adk_fan_in_state.py
```

Real captured output:

```
A) Two parallel nodes write state['summary'] -- no reducer declared
   equal timing             -> summary = 'keywords=[ai,agents]'
   sentiment finishes last  -> summary = 'sentiment=positive'
   keywords finishes last   -> summary = 'keywords=[ai,agents]'
   (no error, no warning -- the last delta committed simply wins)

B) The fix: branch-private keys + a JoinNode that aggregates outputs
   final state sentiment: 'positive'
   final state keywords:  '[ai, agents]'
   JoinNode aggregate:    {'keywords': {'keywords': ['ai', 'agents']}, 'sentiment': {'sentiment': 'positive'}}
```

In Part A the two branches are given controlled delays only to make the point
visible: the branch that **finishes last** overwrites the key. With equal
timing the result is still whichever branch the scheduler happens to commit
last — here the second-declared one. No error and no warning is raised. The
output is byte-stable across repeated runs (the aggregate dict in Part B is
printed with sorted keys so its ordering does not vary).

## Run the LangGraph contrast

```bash
python langgraph_contrast.py
```

Real captured output:

```
InvalidUpdateError: At key 'summary': Can receive only one value per step. Use an Annotated key to handle multiple values.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE
```

LangGraph raises rather than silently picking a winner: a key written by two
nodes in the same superstep needs an `Annotated` reducer or it is an error.

## Takeaway

ADK 2.0's `Workflow` treats parallel state writes as last-delta-wins. If two
branches can touch the same key, give each branch its own key and combine them
in a `JoinNode` (or a single downstream node), or the value you keep depends on
scheduling order.

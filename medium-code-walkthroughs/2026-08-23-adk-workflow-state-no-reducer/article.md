# I Fanned Out Two ADK 2.0 Nodes to the Same State Key. One Silently Won — No Reducer, No Error.

I was porting a small fan-out graph from LangGraph to Google's Agent Development Kit. Two branches ran in parallel, each computed a piece of a summary, and both wrote it to the same state field. In LangGraph that graph refuses to run. In ADK 2.0 it ran fine on the first try, and quietly threw one of the two results away.

That silence is the interesting part. ADK 2.0's new Workflow Runtime looks and reads a lot like LangGraph: you declare nodes, wire edges, fan out, fan in. If you carry over LangGraph's mental model, you will assume the framework protects you from concurrent writes to the same state key. It does not. Here is exactly what happens, why, and the two-line change that fixes it.

## Why this is a 2026 problem

The Workflow Runtime is new. Google shipped `google-adk` 2.0.0 on May 19, 2026 ([PyPI release history](https://pypi.org/project/google-adk/)), and the [v2.0.0 release notes](https://github.com/google/adk-python/releases/tag/v2.0.0) describe it as a "model-agnostic engine for orchestrating non-linear, conditional, and cyclical agent execution patterns" with "parallel sub-agent workers." That is a graph engine, and graph engines invite the fan-out/fan-in patterns where concurrent state writes actually collide. Everything below was run on the current release, `google-adk` 2.7.1 (August 17, 2026), against `langgraph` 1.2.11.

The behavior is not exotic or contrived. Fan-out to parallel workers and merge their results is the single most common reason to reach for a graph in the first place.

## The setup: a fan-out that writes one key

A `Workflow` node in ADK 2.0 is built from edges. A `FunctionNode` wraps a plain Python function; by default its parameters are read from the workflow's shared state, and to write state the function mutates `ctx.state`. That write is captured as a state delta and persisted by the session.

Here is a fan-out where both parallel branches write the same key, `summary`:

```python
class State(BaseModel):
    topic: str = ""
    summary: str = ""          # collision: two branches write this

async def sentiment(ctx, topic: str):
    ctx.state["summary"] = "sentiment=positive"     # same key...

async def keywords(ctx, topic: str):
    ctx.state["summary"] = "keywords=[ai,agents]"   # ...as this one

start_n = FunctionNode(func=start, name="start")
Workflow(name="collide", state_schema=State, edges=[
    (START, start_n),
    (start_n, (FunctionNode(func=sentiment, name="sentiment"),
               FunctionNode(func=keywords, name="keywords"))),
])
```

The tuple `(start_n, (sentiment, keywords))` is the fan-out: after `start_n` completes, both `sentiment` and `keywords` become runnable in parallel. The `state_schema=State` is not decoration; ADK validates every `ctx.state` mutation against it at runtime. But it validates *types*, not *concurrency*. Two `str` writes to `summary` are both individually valid.

## What actually happens

I ran the fan-out three times, changing only how long each branch sleeps before it writes, so the ordering is visible instead of down to scheduler luck:

```
A) Two parallel nodes write state['summary'] -- no reducer declared
   equal timing             -> summary = 'keywords=[ai,agents]'
   sentiment finishes last  -> summary = 'sentiment=positive'
   keywords finishes last   -> summary = 'keywords=[ai,agents]'
   (no error, no warning -- the last delta committed simply wins)
```

Three things stand out. First, no exception and no log warning: the workflow completes and reports success. Second, only one write survives; the other is gone. Third, which one survives is decided by completion order: the branch that finishes last overwrites the key. When both branches finish at effectively the same time ("equal timing"), the winner is whichever the scheduler commits last, which here is the second-declared branch. That is stable on my machine but it is an implementation detail, not a guarantee you should lean on.

The mechanism is straightforward once you look at the source. Each node's `ctx.state` mutations become a `state_delta` attached to that node's event, and the session applies deltas in the order the events are committed. There is no merge function, no conflict check, no per-branch isolation of the `summary` key. Last delta in, last value kept.

*Figure 1 — Both parallel branches target the single `state['summary']` slot; ADK keeps whichever delta is committed last.*

## How LangGraph handles the same thing

This is where the ported-from-LangGraph reflex comes from. I wrote the identical pattern with LangGraph 1.2.11: two nodes fanning out from `START`, both returning the `summary` key, no reducer annotation:

```python
class State(TypedDict):
    summary: str          # no reducer annotation

def sentiment(state): return {"summary": "sentiment=positive"}
def keywords(state):  return {"summary": "keywords=[ai,agents]"}
# both edges: START -> sentiment, START -> keywords  (same superstep)
```

Running it does not pick a winner. It raises:

```
InvalidUpdateError: At key 'summary': Can receive only one value per step. Use an Annotated key to handle multiple values.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE
```

LangGraph treats "two nodes wrote one key in one step" as a programming error unless you have explicitly told it how to combine the values, using an `Annotated` type with a reducer such as `operator.add`. The framework refuses to guess. That is the guarantee people internalize — and then unknowingly expect from every other graph library.

ADK 2.0 makes the opposite choice: it never raises here, it just applies the writes in order. Neither choice is wrong on its own. The danger is assuming you have LangGraph's guardrail when you are running on ADK's.

## The fix: give each branch its own key

The moment you stop sharing a key, the ambiguity disappears. Have each branch write a distinct, branch-private field, and combine them explicitly in a downstream node. ADK ships a `JoinNode` for exactly this: it waits for all of its predecessors and hands their outputs to the next step, keyed by node name:

```python
def sentiment(ctx, topic: str):
    ctx.state["sentiment"] = "positive"             # private key
    return {"sentiment": "positive"}

def keywords(ctx, topic: str):
    ctx.state["keywords"] = "[ai, agents]"          # private key
    return {"keywords": ["ai", "agents"]}

join = JoinNode(name="join")
Workflow(name="fan_in", state_schema=State, edges=[
    (START, start_n), (start_n, (sen, kw)), (sen, join), (kw, join),
])
```

Real output:

```
B) The fix: branch-private keys + a JoinNode that aggregates outputs
   final state sentiment: 'positive'
   final state keywords:  '[ai, agents]'
   JoinNode aggregate:    {'keywords': {'keywords': ['ai', 'agents']}, 'sentiment': {'sentiment': 'positive'}}
```

Now both results survive. The two state keys never contend because they are different keys, and the `JoinNode` collects each branch's return value into a dict keyed by the producing node. (The dict's key order still reflects completion order, so I sort it for a stable printout — but both entries are always present, which is the point.) This is the pattern to reach for whenever a fan-out needs to feed a single downstream step.

*Figure 2 — Branch-private keys plus a `JoinNode`: nothing is overwritten because nothing is shared.*

If you genuinely need the two branches to write a single field — accumulating into a list, say — ADK will not build the reducer for you the way `Annotated[list, operator.add]` does in LangGraph. You either serialize those writes through one node, or you aggregate in a `JoinNode` and reduce there yourself.

## Try It Yourself

Two files, both fully offline — no model, no API key, no network calls. The full runnable versions are in the [code walkthrough repo](https://github.com/krpraveen0/linkedin-agent/tree/develop/medium-code-walkthroughs).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "google-adk==2.7.1" "langgraph==1.2.11"
python adk_fan_in_state.py
```

Captured output, byte-for-byte:

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

Then run the contrast and watch LangGraph refuse the same shape:

```bash
python langgraph_contrast.py
```

```
InvalidUpdateError: At key 'summary': Can receive only one value per step. Use an Annotated key to handle multiple values.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE
```

Change the sleep values in `adk_fan_in_state.py` and the ADK winner flips with them. That is the whole lesson in one knob: in ADK 2.0, timing decides which write you keep.

## Key Takeaways

- **ADK 2.0's Workflow Runtime has no state reducer.** Two parallel nodes writing the same `ctx.state` key is last-delta-wins, applied in completion order, with no exception and no warning (verified on `google-adk` 2.7.1).
- **The winner is timing-dependent.** The branch that finishes last overwrites the key; with a near-tie it comes down to scheduler order, which you should not treat as stable.
- **`state_schema` does not save you.** It validates the type of each write, not the fact that two writes raced for one key.
- **LangGraph makes the opposite call.** The same pattern raises `InvalidUpdateError` unless you declare an `Annotated` reducer — so don't port LangGraph's safety assumption over unexamined.
- **The fix is structural.** Give each branch a private key and merge them in a `JoinNode` (or a single downstream node). Don't let two branches share one key unless a single node owns that write.

*This walkthrough validates traceability, freshness, and real code execution — not deep domain correctness. Behavior can change between ADK releases, so re-check against your pinned version, and give any production how-to a human accuracy pass.*

## Sources

- [google-adk on PyPI — release history (2.0.0 on 2026-05-19, 2.7.1 on 2026-08-17)](https://pypi.org/project/google-adk/)
- [google/adk-python v2.0.0 release notes](https://github.com/google/adk-python/releases/tag/v2.0.0)
- [google/adk-python repository](https://github.com/google/adk-python)
- [LangGraph — INVALID_CONCURRENT_GRAPH_UPDATE error reference](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE) (also printed by the reproduction above)
- Behavior verified locally on `google-adk` 2.7.1 and `langgraph` 1.2.11, Python 3.11 (this article's runnable code)

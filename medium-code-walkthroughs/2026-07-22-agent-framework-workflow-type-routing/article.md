# Microsoft's Agent Framework Routes Workflow Messages by Python Type — and Runs Them in Pregel Supersteps

If you draw a Microsoft Agent Framework workflow as boxes and arrows, you will get the arrows wrong. An arrow from your classifier node to your refund node does not mean "the classifier calls the refund node." It means "if the classifier emits a message whose type the refund node has a handler for, deliver it." The edge is a conditional pipe keyed on Python types, not a function call. Miss that, and you will wire a graph that looks correct and silently drops half its messages.

This is the part of the framework worth understanding before you build anything real on it, so this article does two things: it shows the type-based routing behavior with a runnable example, and it confirms — by reading the shipped source of the installed package, not the marketing — that the engine underneath is a Pregel-style superstep loop.

## Why this is worth your attention now

Microsoft Agent Framework is the merger of two of Microsoft's agent efforts: AutoGen (the multi-agent research project) and Semantic Kernel (the enterprise SDK). It landed in public preview on [October 1, 2025](https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/) and reached a production-ready 1.0 in April 2026, described by Microsoft as a release with "stable APIs" and long-term support ([Visual Studio Magazine, April 6, 2026](https://visualstudiomagazine.com/articles/2026/04/06/microsoft-ships-production-ready-agent-framework-1-0-for-net-and-python.aspx)). Development has stayed fast: the Python package `agent-framework-core` shipped version **1.12.0 on July 21, 2026** ([GitHub releases](https://github.com/microsoft/agent-framework/releases)). That is the version every command and output below was run against.

The reason the routing model matters more here than in a typical framework is lineage. AutoGen users are used to a `GroupChat` where agents take turns; Semantic Kernel users are used to imperative orchestration. Agent Framework's `Workflow` is neither. It is a typed message graph, and the two habits above will both mislead you.

## The mental model: a message graph, not a call graph

A workflow is built from **executors** (nodes) connected by **edges**. Each executor registers one or more handlers, and a handler declares the message type it accepts through its parameter annotation. When you connect executor A to executor B with an edge, you are saying: "whatever A sends, offer it to B — B will accept it only if B has a handler for that message's type."

Two consequences fall out of this, and both surprise people:

1. A single edge can carry different message types to different handlers on the same target.
2. If a target has no handler for the type that arrives, the edge simply does not deliver — no error, no warning, nothing runs.

Let's watch both happen.

## Routing is by type, not by the arrow you drew

Here is a support-ticket workflow. A `Classifier` turns a `Ticket` into either a `Refund` or a `Question`. Downstream sit two nodes wired with *identical* edges: a `RefundDesk` that handles both `Refund` and `Question`, and an `FAQ` that handles only `Question`.

```python
class Classifier(Executor):
    @handler
    async def classify(self, t: Ticket, ctx: WorkflowContext[Refund | Question]) -> None:
        if "refund" in t.text.lower():
            await ctx.send_message(Refund(amount=42))
        else:
            await ctx.send_message(Question(text=t.text))

class RefundDesk(Executor):          # handles BOTH types
    @handler
    async def on_refund(self, r: Refund, ctx: WorkflowContext[None, str]) -> None:
        print("  RefundDesk.on_refund invoked")
        await ctx.yield_output(f"RefundDesk paid ${r.amount}")
    @handler
    async def on_question(self, q: Question, ctx: WorkflowContext[None, str]) -> None:
        print("  RefundDesk.on_question invoked")
        await ctx.yield_output(f"RefundDesk relayed: {q.text}")

class FAQ(Executor):                 # handles ONLY Question
    @handler
    async def on_question(self, q: Question, ctx: WorkflowContext[None, str]) -> None:
        print("  FAQ.on_question invoked")
        await ctx.yield_output(f"FAQ answered: {q.text}")

wf = (WorkflowBuilder(start_executor=c, output_from="all")
      .add_edge(c, r)   # identical wiring
      .add_edge(c, f)   # identical wiring
      .build())
```

The classifier is wired to both downstream nodes the same way. Which handler fires is decided at runtime by the *type* of the message, not by the topology. Running it:

```text
refund_desk handles: ['Question', 'Refund']
faq         handles: ['Question']

[Refund ticket] -> Refund is a type only RefundDesk handles
  RefundDesk.on_refund invoked
outputs: ['RefundDesk paid $42']

[Plain question] -> Question is a type BOTH downstream nodes handle
  RefundDesk.on_question invoked
  FAQ.on_question invoked
outputs: ['RefundDesk relayed: What are your opening hours?', 'FAQ answered: What are your opening hours?']
```

Read the two cases. A `Refund` reaches `RefundDesk` and *not* `FAQ` — the trace line for `FAQ` never prints, even though the classifier→FAQ edge exists. A `Question` reaches *both*, because both declare a handler for it. The edge did not decide the destination; the type did.

*Figure 1 — the same two edges deliver different messages depending on the runtime message type.*

This is not incidental behavior. It is enforced at the edge. I confirmed it by reading the installed package rather than trusting the docs: in `agent_framework/_workflows/_edge_runner.py`, every delivery is gated on `self._can_handle(edge.target_id, message)`, and `Executor.can_handle` (in `_executor.py`) is literally:

```python
return any(is_instance_of(message.data, message_type) for message_type in self._handlers)
```

So an edge delivers a message only when the target executor has a handler whose type the message is an instance of. That single line is the whole routing rule.

## The engine underneath: Pregel supersteps

The second thing to internalize is *when* executors run. Agent Framework does not run your graph as a depth-first cascade of calls. It runs it in **supersteps** — the bulk synchronous parallel (BSP) model popularized by Google's Pregel graph engine. In each superstep, every executor with a pending message runs; all messages they emit are collected; then a barrier closes the superstep and those new messages become the input to the next one.

I did not take the docs' word for this either. The runner class in the installed 1.12.0 source, `agent_framework/_workflows/_runner.py`, opens with the docstring:

```text
"""A class to run a workflow in Pregel supersteps."""
```

The practical consequence is the barrier. A fan-in node does not run once per upstream message; it waits until *every* upstream node in the superstep has finished, then runs once with all their outputs collected as a list. Here is an order-approval workflow that fans out to a fraud check and a stock check, then fans in to approval:

```python
wf = (WorkflowBuilder(start_executor=d, output_from="all")
      .add_fan_out_edges(d, [fr, st])
      .add_fan_in_edges([fr, st], ap)
      .build())

supersteps: dict[int, list[str]] = {}
current = 0
async for ev in wf.run(Order("A1001"), stream=True):
    if ev.type == "superstep_started":
        current = ev.iteration
        supersteps[current] = []
    elif ev.type == "executor_invoked" and current:
        supersteps[current].append(ev.executor_id)
    elif ev.type == "output":
        print("OUTPUT:", ev.data)
```

Streaming the events and grouping the invocations by superstep shows the structure exactly:

```text
OUTPUT: APPROVED with fraud=ok(A1001) & stock=ok(A1001)
superstep 1: ran ['fraud', 'stock']
superstep 2: ran ['approve']
```

`fraud` and `stock` both run in superstep 1 — concurrently, not in sequence. `approve` does not run until superstep 2, after the barrier, and it receives both results together (`fraud=ok & stock=ok`). If you have ever hand-written a "wait for all N parallel tasks before continuing" join, the framework's fan-in edge is that barrier, handed to you.

*Figure 2 — fan-out executors share one superstep; the fan-in node runs in the next, after the barrier.*

## What this changes about how you build

The type-graph model has real ergonomic payoffs once you stop fighting it. You route by defining message types and handlers, not by writing `if` ladders inside a monolithic orchestrator. Adding a new branch means adding a new executor with a handler for a new type and an edge — the routing follows automatically. Adding an `AgentExecutor` (an LLM-backed agent wrapped as a node) into any of these positions works the same way; the workflow engine described here is model-agnostic, which is why every example above ran locally with no API key.

The failure mode is equally real: because an unhandled type is silently dropped rather than raising, a typo in a handler's annotation or a message type nobody consumes produces a workflow that runs to completion and does nothing. When a branch "just doesn't fire," check the handler's parameter type against the actual type being sent before you check anything else.

## Try It Yourself

Everything above runs on a laptop, CPU-only, no API key. Two files, about 75 lines each.

```bash
pip install agent-framework-core          # tested on 1.12.0
python 01_type_routing.py
python 02_supersteps.py
```

`01_type_routing.py` produces the routing trace shown above — flip a ticket's text between `"refund"` and a plain question and watch which handlers print. `02_supersteps.py` produces the superstep grouping — add a third checker to the fan-out list and you will see it join `superstep 1` alongside `fraud` and `stock`, while `approve` stays in `superstep 2`. Both files, with their captured output, are in the walkthrough folder linked in Sources.

## Key Takeaways

- In Microsoft Agent Framework, edges are typed pipes: a message is delivered to a target executor only if the target has a handler whose annotated type the message is an instance of. Wiring alone does not determine routing.
- The same edge can carry different types to different handlers, and an unhandled type is dropped silently — no error. A branch that "doesn't fire" is usually a type mismatch.
- The execution engine is a Pregel-style superstep (BSP) loop, confirmed in the installed 1.12.0 source. Fan-out nodes share a superstep and run concurrently; a fan-in node waits for the barrier and runs in the next superstep with all inputs collected.
- Both behaviors are verifiable in minutes, locally, with no model or API key, because the workflow engine is separate from the agents it can host.

## Sources

- Introducing Microsoft Agent Framework — Microsoft Azure Blog, Oct 1, 2025: https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/
- Microsoft Ships Production-Ready Agent Framework 1.0 — Visual Studio Magazine, Apr 6, 2026: https://visualstudiomagazine.com/articles/2026/04/06/microsoft-ships-production-ready-agent-framework-1-0-for-net-and-python.aspx
- Microsoft Agent Framework releases (`python-1.12.0`, Jul 21, 2026): https://github.com/microsoft/agent-framework/releases
- Microsoft Agent Framework Workflows documentation: https://learn.microsoft.com/en-us/agent-framework/workflows/
- Primary evidence: the installed `agent-framework-core` 1.12.0 source — `_runner.py` ("A class to run a workflow in Pregel supersteps"), `_edge_runner.py` and `_executor.py` (`can_handle` type gate).
- Runnable code (auto-generated by the daily-medium-article cloud routine): PR link in the walkthrough folder README.

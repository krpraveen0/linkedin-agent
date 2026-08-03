# LangGraph's `interrupt()` Doesn't Pause Your Node. It Restarts It — So Everything Before It Runs Twice.

You add a human approval step to a LangGraph agent. The node charges a card, then calls `interrupt()` to wait for a reviewer to click "approve." The reviewer clicks approve. The card gets charged a second time. Nothing crashed, no retry policy fired, and the logs show the node ran cleanly, twice.

This is not a bug in your code. It is exactly how `interrupt()` is documented to work, and the documentation lives inside the package you already installed. On LangGraph 1.2.10 (released [July 28, 2026](https://pypi.org/pypi/langgraph/json), six days before this was written), the docstring for `interrupt` says it plainly:

> The graph resumes from the start of the node, **re-executing** all logic.

That one sentence is the whole article. The rest is watching it happen, understanding why, and moving your side effects to the one place where they only fire once.

## The human-in-the-loop API that everyone reaches for

Since [LangGraph 1.0](https://pypi.org/pypi/langgraph/json) went GA in October 2025, `interrupt()` plus `Command(resume=...)` has been the standard way to put a human in the loop. The shape is simple and it reads like a blocking call:

```python
def checkout(state):
    charge_card(state["amount"])                    # side effect
    decision = interrupt("Approve this charge?")    # pause for a human
    return {"approved": decision}
```

You call `interrupt()` with a value. LangGraph raises a `GraphInterrupt`, persists the graph to the checkpointer, and hands your value back to the caller. Later, you resume by invoking the graph again with `Command(resume="yes")`, and the string `"yes"` becomes the return value of `interrupt()`. The official [interrupts guide](https://docs.langchain.com/oss/python/langgraph/interrupts) presents it exactly this way.

It looks like `interrupt()` is a breakpoint that freezes the stack and thaws it on resume. It is not. There is no stack to freeze. When you resume, LangGraph reloads the checkpoint and runs the node function again from its first line. Every statement above `interrupt()` executes a second time.

## Watch the card get charged twice

Here is a self-contained graph with a stand-in side effect: appending to a list instead of hitting a payment API, so you can run it with no keys and no network. The `charges.append(...)` sits *before* the interrupt, which is precisely the mistake.

```python
from typing_extensions import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command

charges = []

class State(TypedDict):
    amount: int
    approved: str

def checkout(state: State):
    charges.append(state["amount"])                       # side effect BEFORE interrupt
    print(f"  charge_card(${state['amount']})  -> charges so far: {charges}")
    decision = interrupt(f"Approve charge of ${state['amount']}?")
    print(f"  resumed with decision: {decision!r}")
    return {"approved": decision}

builder = StateGraph(State)
builder.add_node("checkout", checkout)
builder.add_edge(START, "checkout")
graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "order-1"}}

print("first invoke (runs up to the interrupt):")
result = graph.invoke({"amount": 42}, config)
print(f"  __interrupt__ surfaced: {bool(result.get('__interrupt__'))}")

print("resume with Command(resume='yes'):")
final = graph.invoke(Command(resume="yes"), config)
print(f"  final state: approved={final['approved']!r}")

print(f"\nTIMES THE CARD WAS CHARGED: {len(charges)}  (amounts: {charges})")
```

Running it prints:

```
first invoke (runs up to the interrupt):
  charge_card($42)  -> charges so far: [42]
  __interrupt__ surfaced: True
resume with Command(resume='yes'):
  charge_card($42)  -> charges so far: [42, 42]
  resumed with decision: 'yes'
  final state: approved='yes'

TIMES THE CARD WAS CHARGED: 2  (amounts: [42, 42])
```

The `charge_card` line appears twice. `charges` ends as `[42, 42]`. The first invoke ran the append and then hit the interrupt; the resume ran the *entire node again*, including the append, before `interrupt()` returned the value you passed in. A checkpointer is mandatory for `interrupt()`, and here it is doing its job perfectly: it restores the node's starting state and replays the function. The checkpointer is behaving as designed; the replay is the whole point of it.

## Why it works this way

LangGraph executes nodes in discrete steps called supersteps, and it checkpoints *between* them, not in the middle of one. There is no mechanism to snapshot a Python function halfway through a line and resume the interpreter there. So when a node needs to wait for outside input, LangGraph's only durable unit of work is the whole node. It saves the state that entered the node, unwinds, and on resume feeds that saved state back in and runs the function again.

The resume value is the one thing that changes on the second pass. LangGraph keeps a per-task list of resume values; when execution reaches the matching `interrupt()` call again, instead of raising `GraphInterrupt` it returns the stored value and lets the function continue past it. Everything textually above that call has no idea it is running for the second time.

That means the rule is mechanical and easy to apply: **code above an `interrupt()` runs once per resume; code below the last resumed `interrupt()` runs once.** Side effects belong below.

## The fix is to ask first, act second

Move the side effect after the interrupt. The node now asks for approval before it does anything irreversible:

```python
def checkout(state: State):
    decision = interrupt(f"Approve charge of ${state['amount']}?")  # ask FIRST
    if decision == "yes":
        charges.append(state["amount"])                            # runs once, after resume
        print(f"  charge_card(${state['amount']}) -> charges: {charges}")
    return {"approved": decision}
```

Same graph, same resume call, different output:

```
  charge_card($42) -> charges: [42]
  final state: approved='yes'

TIMES THE CARD WAS CHARGED: 1  (amounts: [42])
```

One charge. The lines before the interrupt on the first pass were only the interrupt itself, so the replay had nothing to duplicate. The payment now lives on the far side of the human decision, where it executes exactly once. If you have setup work that genuinely must run before the pause (reading a record, computing a total), either make it idempotent, or split it into its own node ahead of the approval node so the interrupt node contains nothing but the question and the action.

## Two interrupts, one node, three executions

The replay model has a sharper edge when a node contains more than one `interrupt()`. Resume values are matched to interrupts strictly by order, and each resume replays the node up to the next unanswered interrupt. Watch how many times the node body runs when you collect two fields:

```python
log = []

def form(state):
    log.append("node-start")
    name = interrupt("what is your name?")
    age = interrupt("what is your age?")
    return {"name": name, "age": age}

# invoke, then resume twice
graph.invoke({}, config)                            # stops at 1st interrupt
r1 = graph.invoke(Command(resume="Ada"), config)    # answers 1st, stops at 2nd
print(f"  after 1st resume, interrupted again? {bool(r1.get('__interrupt__'))}")
final = graph.invoke(Command(resume="36"), config)  # answers 2nd, finishes
print(f"  final: name={final['name']!r} age={final['age']!r}")
print(f"\nnode-start ran {log.count('node-start')} times: {log}")
```

Output:

```
  after 1st resume, interrupted again? True
  final: name='Ada' age='36'

node-start ran 3 times: ['node-start', 'node-start', 'node-start']
```

Two interrupts, and the node body executed three times: once for the initial invoke, once for each resume. The resume matching is positional, which is why the docstring warns that reordering or conditionally skipping `interrupt()` calls between runs will hand a resume value to the wrong prompt. This is also where a still-open issue, [#7780](https://github.com/langchain-ai/langgraph/issues/7780) (filed May 13, 2026), bites people: put an `interrupt()` inside a `while` loop and the replayed earlier iterations consume previously provided resume values, firing their logic again. The advice is the same everywhere it shows up: keep interrupt nodes small, and keep side effects out of the re-executed region.

## Try It Yourself

Everything above runs offline with no model and no API key. One `pip install`, three scripts.

```bash
python3 -m venv .venv
./.venv/bin/pip install "langgraph==1.2.10"
./.venv/bin/python demo1_double_execution.py   # charges twice: [42, 42]
./.venv/bin/python demo2_fix.py                # charges once:  [42]
./.venv/bin/python demo3_multi_interrupt.py    # node body runs 3 times
```

You can confirm the governing sentence yourself without reading any website, because it ships in the package:

```bash
./.venv/bin/python -c "from langgraph.types import interrupt; print(interrupt.__doc__)"
```

The output includes the line *"The graph resumes from the start of the node, re-executing all logic."* Direct inspection of the installed 1.2.10 package agrees with the published docs, so you are not taking a blog's word for it, including this one.

## Key Takeaways

- `interrupt()` is not a coroutine-style pause. On resume, LangGraph reloads the checkpoint and **runs the whole node again from its first line**; only the resumed `interrupt()` call returns a value instead of raising.
- Any side effect placed *before* `interrupt()` runs again on every resume. A payment, an email, or an insert written there will fire twice (or more).
- Put irreversible work *after* the interrupt, make pre-interrupt work idempotent, or isolate setup in a separate upstream node.
- Multiple `interrupt()` calls in one node match resume values by position, and each resume replays the node up to the next unanswered one — so a node with two interrupts executes its body three times across a full run.
- This is documented behavior in LangGraph 1.x (1.0 GA October 2025; 1.2.10 on July 28, 2026), confirmed by the installed package's own docstring — not an edge case that a version bump will quietly fix.

## Sources

- LangGraph `interrupt` docstring, direct inspection of installed `langgraph==1.2.10` (verified 2026-08-03) — "The graph resumes from the start of the node, re-executing all logic."
- [LangGraph interrupts guide](https://docs.langchain.com/oss/python/langgraph/interrupts) and [`interrupt` API reference](https://reference.langchain.com/python/langgraph/types/interrupt), LangChain docs (accessed 2026-08-03)
- [langgraph release history on PyPI](https://pypi.org/pypi/langgraph/json) — 1.0.0 (2025-10-17), 1.2.10 (2026-07-28)
- [langchain-ai/langgraph issue #7780, "Interrupt() in a loop will cause extra resumes"](https://github.com/langchain-ai/langgraph/issues/7780) — open, filed 2026-05-13

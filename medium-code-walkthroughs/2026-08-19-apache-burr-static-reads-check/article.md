# I Forgot One Line in My Burr Action. It Read My Source Code and Refused to Build.

I gave a Burr action a list of the state keys it reads. Then I touched a key that wasn't on the list. Before the application built, before a single step ran, before any LLM was called, Burr stopped me with an error naming the exact key I'd left out:

```
ValueError: Action reads undeclared state keys: ['limit']. Declared reads: ['turn']
```

It didn't run my function to find that out. It read the function's source, parsed it into a syntax tree, and compared what I *touch* against what I *declared*. That is an unusual thing for an agent framework to do, and it is worth understanding exactly — because the check is real, it fires earlier than you'd expect, and it has two blind spots that will let a bug straight through if you don't know they're there.

## Why Burr, why now

[Burr](https://github.com/apache/burr) is a small Python library for building stateful applications — chatbots, agents, simulations — as explicit state machines. You write actions, wire transitions between them, and Burr runs the loop while tracking every state change.

The reason to look at it this month is the package itself. If you run `pip install burr` today, you get a redirect:

```
Name: burr
Version: 0.42.0
Summary: This package has moved to apache-burr. Install apache-burr instead.
Requires: apache-burr
```

Burr was donated by DAGWorks to the Apache Software Foundation and is now developed as **Apache Burr (incubating)** ([incubation proposal](https://cwiki.apache.org/confluence/display/INCUBATOR/BurrProposal)). The `burr` name on PyPI is now a thin shim that pins [`apache-burr`](https://pypi.org/project/apache-burr/), whose current release, `0.42.0`, [went up on 2026-05-10](https://pypi.org/project/apache-burr/#history). The import path stays `burr`, so your code doesn't change — but the package you actually run is the Apache one, and that's the one whose behavior this article inspects.

Everything below was verified directly against `apache-burr==0.42.0` on Python 3.11.

## The honest version

Every Burr action declares two things: the state keys it `reads` and the keys it `writes`. Here is a tiny agent-style loop that takes turns until it hits a limit, and it declares its keys honestly:

```python
from burr.core import action, State, ApplicationBuilder, expr

@action(reads=["turn", "limit"], writes=["turn"])
def take_turn(state: State) -> State:
    return state.update(turn=state["turn"] + 1)

@action(reads=["turn"], writes=[])
def report(state: State) -> State:
    return state

app = (
    ApplicationBuilder()
    .with_actions(take_turn=take_turn, report=report)
    .with_transitions(
        ("take_turn", "take_turn", expr("turn < limit")),
        ("take_turn", "report", expr("turn >= limit")),
    )
    .with_state(turn=0, limit=3)
    .with_entrypoint("take_turn")
    .build()
)

_, _, s = app.run(halt_after=["report"])
print("final turn:", s["turn"], "/ limit:", s["limit"])
```

`take_turn` reads `turn` and `limit`, writes `turn`. It runs three times and stops:

```
final turn: 3 / limit: 3
```

Nothing surprising yet. The surprise is what happens when the declaration and the code disagree.

## Forget one read

Say I drop `limit` from the `reads` list but still use it in the body:

```python
@action(reads=["turn"], writes=["turn"])   # "limit" is gone
def take_turn_buggy(state: State) -> State:
    ceiling = state["limit"]               # ...but still read here
    return state.update(turn=state["turn"] + 1)
```

In most frameworks you'd find out at runtime, when `state["limit"]` throws a `KeyError` — or worse, you wouldn't find out at all, because the key happens to be present for other reasons. Burr finds out at *decoration time*. The moment `@action(...)` wraps the function, it raises:

```
ValueError: Action reads undeclared state keys: ['limit']. Declared reads: ['turn']
```

This isn't a runtime guard and it isn't a build-time guard. It fires when the decorator is applied — before you call `ApplicationBuilder`, before `.build()`, before `app.run()`. If the decorated function is at module top level, the import itself fails.

## What Burr is actually doing

The check lives in a function called `_validate_declared_reads` in [`burr/core/action.py`](https://github.com/apache/burr/blob/main/burr/core/action.py), and its logic is small enough to describe exactly:

1. If you declared no reads at all, it does nothing and returns.
2. It calls `inspect.getsource` on your function. If the source can't be read (say, a lambda in a REPL), it silently returns.
3. It inspects the signature for a parameter **annotated exactly as `State`** to learn the name of your state argument. If no parameter carries that annotation, it returns without checking anything.
4. It parses the source with `ast.parse` and walks the tree for `Subscript` nodes — `state["something"]` — where the subscripted name matches your state parameter and the key is a **string literal**.
5. Every such literal key that isn't in your declared `reads` gets collected. If the list is non-empty, it raises the `ValueError` above.

So this is static analysis of your own code, run at decoration time, keyed on a specific annotation and a specific syntactic shape. That precision is the strength — and, as it turns out, the weakness.

## Where the check goes quiet

Because the analysis is syntactic, it only sees the exact pattern it looks for: a literal string subscript on a parameter it recognizes as the state. Step outside that shape and the check simply doesn't apply. There are two easy ways to do that by accident.

**Blind spot one — don't use a literal subscript.** `state.get("limit")` and `state[key]` (a variable key) are not `Subscript` nodes with a constant string slice, so the visitor never flags them:

```python
@action(reads=["turn"], writes=["turn"])
def via_get(state: State) -> State:
    ceiling = state.get("limit")           # reads "limit", check says nothing
    return state.update(turn=state["turn"] + 1)
```

**Blind spot two — don't annotate the parameter.** If your state argument isn't annotated `state: State`, step 3 above never finds it, and the whole check is skipped:

```python
@action(reads=["turn"], writes=["turn"])
def no_annotation(state):                  # no ': State'
    ceiling = state["limit"]               # literal subscript, but not checked
    return state.update(turn=state["turn"] + 1)
```

Both of these wrap without a peep:

```
== 3a. state.get() is invisible to the check ==
wrapped: no error (state.get is not a literal subscript)

== 3b. no ': State' annotation skips the check ==
wrapped: no error (Burr never found the state parameter)
```

Neither is exotic. Dynamic keys are how you'd read a field whose name comes from config; dropping the annotation is a one-character omission. The check is a helpful linter for the common case, not a wall around your state.

## The asymmetry nobody tells you about

Here's the part that changed how I think about the contract. Burr validates the keys you *read*. It does **not**, for a standard `@action`, validate the keys you *write*. I declared `writes=["turn"]` and then wrote a second key anyway:

```python
@action(reads=["turn"], writes=["turn"])   # only "turn" declared
def take_turn(state: State) -> State:
    return state.update(turn=state["turn"] + 1, log="tick")  # also writes "log"
```

No error at decoration, no error at runtime. The undeclared key lands in state and stays there:

```
declared writes: ['turn']
keys after step: ['log', 'turn']
undeclared 'log' persisted: True -> tick
```

So the mental model "my action's `writes` list is the set of keys it can change" is wrong for the decorator API. The reads list is enforced (statically, in the common case); the writes list, for a single-step `@action`, is documentation the runtime trusts you to honor. That matters when you reason about which actions can touch which state — a reviewer reading your `writes` declaration is reading a promise the framework never checks.

## Try It Yourself

Everything above is one file and about a minute of setup. No API key, no model — the whole point is that Burr's read-checking happens before any of that.

```bash
python -m venv venv && source venv/bin/activate
pip install "burr==0.42.0"   # pulls apache-burr==0.42.0
python agent_state_contract.py
```

The full script and its real output are in the code walkthrough linked under Sources below. Running it prints:

```
== 1. honest loop ==
final turn: 3 / limit: 3

== 2. forgot to declare a read ==
ValueError: Action reads undeclared state keys: ['limit']. Declared reads: ['turn']

== 3a. state.get() is invisible to the check ==
wrapped: no error (state.get is not a literal subscript)

== 3b. no ': State' annotation skips the check ==
wrapped: no error (Burr never found the state parameter)
```

Change a `state["..."]` to a key you didn't declare and watch section 2 catch it at the decorator line. Change it to `state.get("...")` and watch the same access sail through. That contrast is the whole lesson.

## Key Takeaways

- **`pip install burr` now redirects to `apache-burr`.** Burr moved to the Apache Software Foundation as Apache Burr (incubating); the current release is `apache-burr==0.42.0` (2026-05-10). The import path is unchanged.
- **Burr statically validates declared reads.** When `@action` wraps a function, it parses the source and raises `ValueError: Action reads undeclared state keys: [...]` if you read a state key you didn't list — at decoration time, before build or run.
- **The check is syntactic and has two blind spots.** It only flags literal `state["key"]` subscripts, and only when a parameter is annotated `state: State`. `state.get("key")`, variable keys, and un-annotated parameters all skip it.
- **Reads are checked; writes are not.** A standard `@action` can write keys it never declared, and they persist silently. Treat the `writes` list as an honest-intent declaration, not an enforced boundary.
- **Declare your reads with literal subscripts and typed state.** That's the exact shape Burr's validator understands — anything else forfeits the safety net.

**Sources:** [Apache Burr on GitHub](https://github.com/apache/burr) · [`_validate_declared_reads` in burr/core/action.py](https://github.com/apache/burr/blob/main/burr/core/action.py) · [apache-burr on PyPI (0.42.0, 2026-05-10)](https://pypi.org/project/apache-burr/) · [burr redirect shim on PyPI](https://pypi.org/project/burr/) · [Apache Incubator: Burr proposal](https://cwiki.apache.org/confluence/display/INCUBATOR/BurrProposal) · [Apache Burr documentation](https://burr.apache.org/)

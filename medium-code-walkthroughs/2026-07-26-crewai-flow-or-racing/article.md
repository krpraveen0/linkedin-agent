# CrewAI's `or_()` Fires Once on the First Branch — Not Once Per Branch

You wire two parallel steps into a single handler with `@listen(or_(fast, slow))`, expecting the handler to run when each branch finishes. You run it. The handler fires exactly once — with the payload from whichever branch happened to finish first — and never again. The second branch completes, and your handler stays silent.

That is not a bug. It is the documented meaning of `or_()` in [CrewAI Flows](https://docs.crewai.com/en/concepts/flows), and in `crewai` 1.15 there is now source-level machinery whose only job is to make sure the "losing" branches are cancelled out. If you have been treating `or_()` as "run this for any of these events," you have a fan-in bug waiting to happen. This post shows the exact behavior, quotes the runtime code that produces it, and gives you the one-line fix.

Everything below was run against `crewai` **1.15.6**, published to [PyPI](https://pypi.org/project/crewai/) on 2026-07-24. No LLM or API key is involved — every flow method is plain Python, so the control flow is the only thing under test.

## The setup that trips people up

A CrewAI `Flow` is a class of decorated methods. `@start()` methods run first; `@listen(...)` methods wait for an upstream method to emit. To combine triggers, CrewAI gives you two helpers: `or_()` and `and_()`. The [docs](https://docs.crewai.com/en/concepts/flows) describe them plainly — `or_` "trigger[s] the listener method when any of the specified methods emit an output," and `and_` triggers "only when all the specified methods emit an output."

Here is the trap. "Any of the specified methods emit" reads like "each time any one emits." So you write two parallel start methods and a single handler that listens on `or_` of both:

```python
from crewai.flow.flow import Flow, start, listen, or_, and_

fired = []

class TriggerFlow(Flow):
    @start()
    def fast(self):
        fired.append("fast")
        return "fast-done"

    @start()
    def slow(self):
        fired.append("slow")
        return "slow-done"

    @listen(or_(fast, slow))     # run as soon as ANY listed trigger completes
    def on_any(self, payload):
        fired.append(f"on_any<-{payload}")

    @listen(and_(fast, slow))    # run only after ALL listed triggers complete
    def on_all(self, payload):
        fired.append("on_all")
```

Both `fast` and `slow` run. Intuitively you might expect `on_any` to fire twice — once per branch. It does not.

## What actually happens

Running `TriggerFlow().kickoff()` and printing the order the methods actually executed in:

```text
execution order:
  1. fast
  2. slow
  3. on_any<-fast-done
  4. on_all

on_any fired 1 time(s)
on_all fired 1 time(s)
```

`on_any` fired **once**, carrying `fast-done` — the payload of the first branch to complete. When `slow` finished a moment later, `on_any` did not fire again. `on_all`, the `and_()` handler, fired once after both branches were done. This is deterministic: it produces the same result on every run.

So `or_()` is not "fire for any event." It is "fire once, on the first event, then consider yourself satisfied." That distinction is invisible until the branch you *didn't* expect to win happens to finish first, and your handler runs with the wrong payload.

## Why: the racing rule in the runtime

This behavior is not incidental. In `crewai` 1.15.6 the flow runtime (`crewai/flow/runtime/__init__.py`) contains a method called `_build_racing_groups`, and its own comment states the rule exactly:

> Events of a multi-event `or_()` listener race: only the first to fire should trigger it. We map `{frozenset(racing events): listener}`.

The runtime groups the alternative events feeding a single `or_()` listener into a "racing group." When one of them fires, the others in the group are cancelled as triggers for that listener. A second private field, `_fired_or_listeners`, records which `or_()` listeners have already run so they are not re-fired.

The comment is careful about one edge case worth knowing:

> Only events that EXCLUSIVELY feed one OR listener race; an event that also feeds another listener (e.g. an AND) is left alone when a sibling wins. [...] Events nested under an `and_()` branch (e.g. `or_(and_(a, b), c)`) are not alternatives and never race — cancelling one would make the AND unsatisfiable.

In other words, the "only the first wins" cancellation applies to the plain `or_(a, b)` alternatives, and the runtime is deliberately conservative so it never starves a nested `and_()`. The `_fired_or_listeners` set is also cleared for cyclic flows and re-armed when a `@router` emits a fresh signal, which is how a loop can legitimately fire the same `or_()` handler again on a later turn.

### `and_()` is the mirror image

The `and_()` side is simpler and matches intuition. Its definition in `crewai/flow/dsl/_conditions.py` reads: "Return a condition that fires after all triggers fire." The satisfaction check is a plain `all(...)` over the branch events versus `any(...)` for `or_`. In the run above, `on_all` waited for both `fast` and `slow`, then fired exactly once.

## If you want per-branch reactions, use one listener each

The fix is not a flag or a config option — it is to stop asking `or_()` for something it does not offer. If you want a handler to run for *each* branch, give each branch its own listener:

```python
from crewai.flow.flow import Flow, start, listen

hits = []

class FanInFlow(Flow):
    @start()
    def fast(self):
        return "fast-done"

    @start()
    def slow(self):
        return "slow-done"

    @listen("fast")
    def on_fast(self, payload):
        hits.append(f"on_fast<-{payload}")

    @listen("slow")
    def on_slow(self, payload):
        hits.append(f"on_slow<-{payload}")
```

Running this:

```text
handlers that ran: ['on_fast<-fast-done', 'on_slow<-slow-done']
count: 2
```

Two branches, two handler runs, each with the right payload. Reserve `or_()` for what it actually means: "the moment the *first* of these arrives, proceed once." Reserve `and_()` for "wait for all of them." And when you need to touch every branch independently, wire them separately.

Note that `@listen` accepts either the method reference (`or_(fast, slow)`) or the method name as a string (`@listen("fast")`). Both resolve to the same event name internally, because `or_`/`and_` coerce a callable trigger to its `__name__`.

## The other 1.15 gotcha: a method can't listen to itself

While you are auditing your flows, there is a second recent change worth checking against. As of `crewai` **1.15.3** (published 2026-07-16), a flow method may not listen for its own completion event. People reach for this to build a self-looping step:

```python
from crewai.flow.flow import Flow, start, listen

class LoopFlow(Flow):
    @start()
    def kick(self):
        return "go"

    @listen("tick")      # 'tick' listens for the event 'tick' — i.e. itself
    def tick(self):
        return "again"
```

Calling `LoopFlow().kickoff()` raises immediately, before any method runs:

```text
ValidationError: 1 validation error for LoopFlow
  Value error, methods.tick.listen must not reference itself [type=value_error, ...]
```

The rejection happens inside `FlowDefinition` validation — a Pydantic `model_validator` named `_validate_trigger_namespace` raises `methods.{name}.listen must not reference itself`. If you want a loop, drive it with a `@router` that emits a distinct signal name and listen for *that*, not for the method's own name.

## Why this is churning right now

CrewAI's Flow condition engine is being actively reworked in mid-2026, which is why these behaviors are worth pinning down empirically rather than from memory. Recent releases moved the `@listen`/`@router` runtime to read from a declarative `FlowDefinition`, simplified condition evaluation to be stateless per event, and added the self-listen rejection — all shipped across the 1.15.x line in July 2026 ([1.15.2](https://pypi.org/project/crewai/) on 2026-07-08, [1.15.3](https://pypi.org/project/crewai/1.15.3/) on 2026-07-16, up to [1.15.6](https://pypi.org/project/crewai/) on 2026-07-24). You can see the `FlowDefinition` path directly: the self-listen error above is a Pydantic validation error raised while building that definition, which is exactly the layer the changelog says the runtime now reads from. Semantics that move this fast reward a five-minute test over an assumption.

## Try It Yourself

Everything here runs offline. No model, no key.

```bash
python -m venv venv && source venv/bin/activate
pip install crewai            # installs 1.15.6
export CREWAI_TRACING_ENABLED=false
python triggers.py            # or_ vs and_
python per_branch.py          # one listener per branch
python selflisten.py          # self-listen rejection
```

`triggers.py` is the first code block above with a `kickoff()` and a print of the recorded order. CrewAI prints its own Rich status panels (one per method) above this; the recorded order is the real, unedited tail of that output:

```text
execution order:
  1. fast
  2. slow
  3. on_any<-fast-done
  4. on_all

on_any fired 1 time(s)
on_all fired 1 time(s)
```

`per_branch.py` prints:

```text
handlers that ran: ['on_fast<-fast-done', 'on_slow<-slow-done']
count: 2
```

And `selflisten.py` raises at `kickoff()`:

```text
ValidationError: 1 validation error for LoopFlow
  Value error, methods.tick.listen must not reference itself [type=value_error, ...]
```

The full scripts and captured output are in the [code walkthrough](#sources) linked below.

## Key Takeaways

- `@listen(or_(a, b))` fires the handler **once**, on the first branch to complete, and passes that branch's payload. It does not fire again for later branches.
- The runtime enforces this with a "racing group": alternative events feeding one `or_()` listener race, and only the first winner triggers it (`_build_racing_groups` in `crewai/flow/runtime/__init__.py`, 1.15.6).
- `and_(a, b)` is the mirror image — it fires once, after **all** branches complete.
- To react to every branch independently, give each branch its own `@listen`, not a shared `or_()`.
- As of `crewai` 1.15.3 (2026-07-16), a method that listens for its own name raises a `ValidationError` at `kickoff()`. Build loops with a `@router` that emits a distinct signal.
- CrewAI's flow condition engine is actively changing in mid-2026; verify these semantics against the version you actually ship.

## Sources

- CrewAI Flows documentation — https://docs.crewai.com/en/concepts/flows
- `crewai` on PyPI (1.15.6, 2026-07-24) — https://pypi.org/project/crewai/
- CrewAI releases (changelog, 1.15.x, July 2026) — https://github.com/crewAIInc/crewAI/releases
- Behavior verified by direct inspection of the installed `crewai` 1.15.6 source (`crewai/flow/runtime/__init__.py`, `crewai/flow/dsl/_conditions.py`, `crewai/flow/flow_definition.py`) and by running the code shown above.
- Code walkthrough for this article (runnable scripts + captured output): see the linked pull request in the delivered version.

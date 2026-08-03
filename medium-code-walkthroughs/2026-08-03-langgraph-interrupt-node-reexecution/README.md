# LangGraph `interrupt()` re-execution — code walkthrough

Companion code for the article **"LangGraph's `interrupt()` Doesn't Pause Your Node. It Restarts It — So Everything Before It Runs Twice."**

Three self-contained scripts prove, with **no model, no API key, and no network at runtime**, that LangGraph resumes a `interrupt()`ed node by re-running the whole node function from its first line. Any side effect placed before `interrupt()` therefore fires again on every resume.

Verified against `langgraph==1.2.10` (released 2026-07-28), Python 3.11.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install "langgraph==1.2.10"
```

## The governing fact (direct package inspection)

```bash
./.venv/bin/python -c "from langgraph.types import interrupt; print(interrupt.__doc__)"
```

The docstring contains, verbatim:

> The graph resumes from the start of the node, **re-executing** all logic.

## Run

### 1. The footgun — side effect before `interrupt()` fires twice

```bash
./.venv/bin/python demo1_double_execution.py
```

Real captured output:

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

### 2. The fix — side effect after `interrupt()` fires once

```bash
./.venv/bin/python demo2_fix.py
```

Real captured output:

```
  charge_card($42) -> charges: [42]
  final state: approved='yes'

TIMES THE CARD WAS CHARGED: 1  (amounts: [42])
```

### 3. Two interrupts, one node — body runs three times

Resume values match interrupts by order; each resume replays the node up to the next unanswered interrupt.

```bash
./.venv/bin/python demo3_multi_interrupt.py
```

Real captured output:

```
  after 1st resume, interrupted again? True
  final: name='Ada' age='36'

node-start ran 3 times: ['node-start', 'node-start', 'node-start']
```

## Takeaway

Code above an `interrupt()` runs once per resume; code below the last resumed `interrupt()` runs once. Keep interrupt nodes small and put irreversible work below the interrupt.

## Files

- `demo1_double_execution.py` — side effect before the interrupt (charges twice)
- `demo2_fix.py` — side effect after the interrupt (charges once)
- `demo3_multi_interrupt.py` — two interrupts, three executions of the node body
- `article.md` — the full article
- `fig1_double_execution.svg`, `fig2_fix.svg` — diagrams

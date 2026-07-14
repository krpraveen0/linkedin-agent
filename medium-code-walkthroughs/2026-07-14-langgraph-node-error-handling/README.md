# LangGraph node-level error handling — working walkthrough

Companion code for the Medium article "Node-Level Error Handling in LangGraph 1.2: A Working
Saga Pattern for Agent Workflows" (2026-07-14).

Both scripts were executed against `langgraph==1.2.9` (released 2026-07-10) in a clean virtualenv;
the printed output in the article is copied verbatim from a real run, not invented.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install langgraph==1.2.9
```

## `saga_recovery.py`

Demonstrates `StateGraph.add_node(..., error_handler=...)`: a `charge_payment` node raises mid-way
through, and a typed `NodeError`-based handler routes to a `refund_and_flag` compensation node
instead of crashing the whole graph run.

```bash
python3 saga_recovery.py
```

Real output:
```
[error_handler] caught failure in node 'charge_payment': payment gateway timeout for order ORD-4471
[final state] {'order_id': 'ORD-4471', 'payment_charged': False, 'status': 'refunded (order ORD-4471 rolled back cleanly)'}
```

Note the gotcha this surfaces: `payment_charged` stays `False` in the final state even though the
node set it to `True` before raising — a node that raises never gets its in-place mutation merged
back into the channel. The compensation node has to explicitly record what actually happened.

## `timeout_demo.py`

Demonstrates `timeout=TimeoutPolicy(run_timeout=...)` actually firing a `NodeTimeoutError`. Requires
an **async** node — LangGraph raises a `ValueError` at `compile()` time if you attach a `timeout` to
a sync node, since synchronous Python can't be cancelled mid-execution.

```bash
python3 timeout_demo.py
```

Real output:
```
[caught] NodeTimeoutError: Node 'slow_call' exceeded its run timeout of 1.000s (elapsed: 1.001s).
```

## Sources for the API surface

- `langgraph.errors.NodeError`, `NodeTimeoutError` and `langgraph.types.TimeoutPolicy` verified
  directly against the installed `langgraph==1.2.9` package via `inspect.signature` and docstrings.
- Node-level error handlers landed in `langgraph` 1.2.0a2 (2026-04-30):
  https://github.com/langchain-ai/langgraph/releases/tag/1.2.0a2
- Stable in `langgraph` 1.2.0 (2026-05-12): https://github.com/langchain-ai/langgraph/releases/tag/1.2.0
- `langgraph` 1.2.9 PyPI release (2026-07-10): https://pypi.org/project/langgraph/1.2.9/
- LangGraph 1.0 durability framing: https://www.langchain.com/blog/langchain-langgraph-1dot0 (2025-10-22)

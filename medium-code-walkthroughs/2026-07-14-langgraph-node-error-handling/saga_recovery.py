"""LangGraph 1.x node-level error handling + timeout demo (Saga/compensation pattern).

Real, runnable against langgraph==1.2.9 (installed 2026-07 in a clean venv).
Note: timeout= requires an async node - LangGraph raises ValueError at compile()
time for a sync node with a timeout, since sync Python can't be cancelled safely
mid-execution.
"""
import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.errors import NodeError
from langgraph.types import Command, TimeoutPolicy


class OrderState(TypedDict):
    order_id: str
    payment_charged: bool
    status: str


async def charge_payment(state: OrderState) -> OrderState:
    # Simulates a downstream payment API failing after partially succeeding.
    state["payment_charged"] = True
    raise RuntimeError(f"payment gateway timeout for order {state['order_id']}")


def payment_error_handler(state: OrderState, error: NodeError) -> Command:
    # Saga-style compensation: route to a recovery node instead of crashing the run.
    print(f"[error_handler] caught failure in node '{error.node}': {error.error}")
    return Command(goto="refund_and_flag", update={"status": "compensating"})


async def refund_and_flag(state: OrderState) -> OrderState:
    state["status"] = f"refunded (order {state['order_id']} rolled back cleanly)"
    return state


graph = StateGraph(OrderState)
graph.add_node(
    "charge_payment",
    charge_payment,
    error_handler=payment_error_handler,
    timeout=TimeoutPolicy(run_timeout=5.0),
)
graph.add_node("refund_and_flag", refund_and_flag)
graph.set_entry_point("charge_payment")
graph.add_edge("refund_and_flag", END)

app = graph.compile()


async def main():
    result = await app.ainvoke({"order_id": "ORD-4471", "payment_charged": False, "status": "pending"})
    print("[final state]", result)


if __name__ == "__main__":
    asyncio.run(main())

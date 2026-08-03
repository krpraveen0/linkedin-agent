"""demo1: interrupt() restarts the node, so code BEFORE it runs twice.

Run:  python demo1_double_execution.py
"""
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command

# A stand-in for a real side effect (charge a card, send an email, insert a row).
charges = []


class State(TypedDict):
    amount: int
    approved: str


def checkout(state: State):
    # This "side effect" sits BEFORE the interrupt.
    charges.append(state["amount"])
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

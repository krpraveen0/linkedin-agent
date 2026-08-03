"""demo2: the fix -- put the side effect AFTER the interrupt, so it runs once.

Run:  python demo2_fix.py
"""
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
    # Ask FIRST. Nothing with a side effect runs before the interrupt.
    decision = interrupt(f"Approve charge of ${state['amount']}?")

    # This runs only after resume, exactly once.
    if decision == "yes":
        charges.append(state["amount"])
        print(f"  charge_card(${state['amount']}) -> charges: {charges}")
    return {"approved": decision}


builder = StateGraph(State)
builder.add_node("checkout", checkout)
builder.add_edge(START, "checkout")
graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "order-2"}}

graph.invoke({"amount": 42}, config)          # pauses at interrupt, no charge yet
final = graph.invoke(Command(resume="yes"), config)

print(f"  final state: approved={final['approved']!r}")
print(f"\nTIMES THE CARD WAS CHARGED: {len(charges)}  (amounts: {charges})")

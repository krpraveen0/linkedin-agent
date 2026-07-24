"""Empirically test LangGraph's `durability` modes and crash-resume replay.

Each node prints a SIDE EFFECT line so we can see, on resume, exactly which
nodes re-run. Node C crashes on its first execution, then succeeds on retry.
"""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

# Count how many times each node's body actually executes (a proxy for
# real side effects: charges, emails, external writes).
CALLS = {"A": 0, "B": 0, "C": 0}
C_SHOULD_CRASH = True


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def node_a(state: State):
    CALLS["A"] += 1
    print("  SIDE EFFECT: node A ran (call #%d)" % CALLS["A"])
    return {"log": ["A"]}


def node_b(state: State):
    CALLS["B"] += 1
    print("  SIDE EFFECT: node B ran (call #%d)" % CALLS["B"])
    return {"log": ["B"]}


def node_c(state: State):
    CALLS["C"] += 1
    print("  SIDE EFFECT: node C ran (call #%d)" % CALLS["C"])
    if C_SHOULD_CRASH and CALLS["C"] == 1:
        raise RuntimeError("node C crashed mid-run (simulated outage)")
    return {"log": ["C"]}


def build(checkpointer):
    g = StateGraph(State)
    g.add_node("A", node_a)
    g.add_node("B", node_b)
    g.add_node("C", node_c)
    g.add_edge(START, "A")
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", END)
    return g.compile(checkpointer=checkpointer)


def run_scenario(durability, thread_id):
    global C_SHOULD_CRASH
    for k in CALLS:
        CALLS[k] = 0
    print("\n=== durability=%r ===" % durability)
    with SqliteSaver.from_conn_string(":memory:") as cp:
        app = build(cp)
        cfg = {"configurable": {"thread_id": thread_id}}

        # First run: node C crashes.
        try:
            app.invoke({"log": []}, cfg, durability=durability)
        except RuntimeError as e:
            print("  -> crashed:", e)

        # What survived the crash in the checkpoint?
        snap = app.get_state(cfg)
        print("  persisted log after crash:", snap.values.get("log"))
        print("  next node(s) to run on resume:", snap.next)

        # Resume: re-invoke with None. C no longer crashes.
        C_SHOULD_CRASH = False
        final = app.invoke(None, cfg, durability=durability)
        C_SHOULD_CRASH = True
        print("  final log:", final["log"])
        print("  total node executions:", dict(CALLS))


if __name__ == "__main__":
    run_scenario("sync", "t-sync")
    run_scenario("exit", "t-exit")

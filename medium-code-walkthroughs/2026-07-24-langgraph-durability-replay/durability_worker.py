"""Worker: runs a 3-node graph against a file-backed checkpointer, then a node
hard-kills the process with os._exit (no exception, no cleanup) to simulate an
OOM/SIGKILL. Argv: <db_path> <durability> <thread_id>.
"""
import operator
import os
import sqlite3
import sys
from typing import Annotated, TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def node_a(state):
    print("  worker: node A completed a superstep")
    return {"log": ["A"]}


def node_b(state):
    print("  worker: node B is about to be hard-killed (os._exit)")
    os._exit(137)  # ungraceful: mimics SIGKILL/OOM, no exception handling runs


def node_c(state):
    return {"log": ["C"]}


def main():
    db_path, durability, thread_id = sys.argv[1], sys.argv[2], sys.argv[3]
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cp = SqliteSaver(conn)
    g = StateGraph(State)
    g.add_node("A", node_a)
    g.add_node("B", node_b)
    g.add_node("C", node_c)
    g.add_edge(START, "A")
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", END)
    app = g.compile(checkpointer=cp)
    app.invoke({"log": []}, {"configurable": {"thread_id": thread_id}},
               durability=durability)


if __name__ == "__main__":
    main()

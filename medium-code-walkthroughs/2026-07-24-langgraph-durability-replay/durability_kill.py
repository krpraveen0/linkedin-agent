"""Driver: for each durability mode, run the worker (which hard-kills itself
during node B), then open the same DB and report what survived the crash.
"""
import operator
import os
import sqlite3
import subprocess
import sys
from typing import Annotated, TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def _rebuild(cp):
    g = StateGraph(State)
    g.add_node("A", lambda s: {"log": ["A"]})
    g.add_node("B", lambda s: {"log": ["B"]})
    g.add_node("C", lambda s: {"log": ["C"]})
    g.add_edge(START, "A")
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", END)
    return g.compile(checkpointer=cp)


def check(durability):
    db = "kill_%s.sqlite" % durability
    if os.path.exists(db):
        os.remove(db)
    tid = "t-" + durability
    print("=== durability=%r : worker runs, then is hard-killed in node B ===" % durability)
    r = subprocess.run([sys.executable, "durability_worker.py", db, durability, tid])
    print("  worker exit code:", r.returncode)

    conn = sqlite3.connect(db, check_same_thread=False)
    app = _rebuild(SqliteSaver(conn))
    snap = app.get_state({"configurable": {"thread_id": tid}})
    print("  state persisted after hard kill:", snap.values.get("log", None))
    print("  next node(s) a resume would run:", snap.next or "(none / restart)")
    print()


if __name__ == "__main__":
    check("sync")
    check("exit")

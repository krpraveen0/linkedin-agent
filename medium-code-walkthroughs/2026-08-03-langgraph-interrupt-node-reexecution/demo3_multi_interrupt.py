"""demo3: two interrupts in one node. Resume values are matched by ORDER,
and everything before an unresolved interrupt re-runs on each resume.

Run:  python demo3_multi_interrupt.py
"""
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command

log = []


class State(TypedDict):
    name: str
    age: str


def form(state: State):
    log.append("node-start")
    name = interrupt("what is your name?")
    age = interrupt("what is your age?")
    return {"name": name, "age": age}


builder = StateGraph(State)
builder.add_node("form", form)
builder.add_edge(START, "form")
graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "form-1"}}

graph.invoke({}, config)                       # stops at 1st interrupt
r1 = graph.invoke(Command(resume="Ada"), config)   # answers 1st, stops at 2nd
print(f"  after 1st resume, interrupted again? {bool(r1.get('__interrupt__'))}")
final = graph.invoke(Command(resume="36"), config) # answers 2nd, finishes

print(f"  final: name={final['name']!r} age={final['age']!r}")
print(f"\nnode-start ran {log.count('node-start')} times: {log}")

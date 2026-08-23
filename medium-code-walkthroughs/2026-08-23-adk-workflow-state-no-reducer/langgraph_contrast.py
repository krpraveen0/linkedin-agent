"""LangGraph's answer to the same pattern: two parallel nodes writing one key."""
from typing import TypedDict
from langgraph.graph import StateGraph, START

class State(TypedDict):
    summary: str          # no reducer annotation

def sentiment(state): return {"summary": "sentiment=positive"}
def keywords(state):  return {"summary": "keywords=[ai,agents]"}

g = StateGraph(State)
g.add_node("sentiment", sentiment)
g.add_node("keywords", keywords)
g.add_edge(START, "sentiment")   # both fan out from START -> same superstep
g.add_edge(START, "keywords")
app = g.compile()

try:
    print(app.invoke({"summary": ""}))
except Exception as e:
    print(f"{type(e).__name__}: {e}")

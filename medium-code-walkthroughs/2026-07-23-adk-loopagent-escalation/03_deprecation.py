"""ADK 2.5.0 emits a DeprecationWarning when you construct a LoopAgent:
the templated workflow agents are being replaced by the graph Workflow runtime
introduced in ADK 2.0 (GA 2026-05-19)."""
import warnings
from google.adk.agents import LoopAgent

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    LoopAgent(name="reviewer", sub_agents=[], max_iterations=3)
    for w in caught:
        if w.category is DeprecationWarning and "LoopAgent" in str(w.message):
            print(str(w.message))

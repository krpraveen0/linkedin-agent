"""A method that listens for its own completion is rejected by CrewAI 1.15."""
from crewai.flow.flow import Flow, start, listen

class LoopFlow(Flow):
    @start()
    def kick(self):
        return "go"

    # 'tick' listens for the event 'tick' — i.e. itself.
    @listen("tick")
    def tick(self):
        return "again"

try:
    LoopFlow().kickoff()
except Exception as e:
    print(f"{type(e).__name__}: {e}")

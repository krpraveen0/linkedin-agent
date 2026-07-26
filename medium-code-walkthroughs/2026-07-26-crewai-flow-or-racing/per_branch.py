"""If you want to react to EACH branch, don't use or_ — use one listener each."""
from crewai.flow.flow import Flow, start, listen

hits = []

class FanInFlow(Flow):
    @start()
    def fast(self):
        return "fast-done"

    @start()
    def slow(self):
        return "slow-done"

    @listen("fast")
    def on_fast(self, payload):
        hits.append(f"on_fast<-{payload}")

    @listen("slow")
    def on_slow(self, payload):
        hits.append(f"on_slow<-{payload}")

FanInFlow().kickoff()
print("handlers that ran:", hits)
print("count:", len(hits))

"""or_ vs and_ in CrewAI Flows: which listener fires, and when.
No LLM or API key required — every method is plain Python."""
from crewai.flow.flow import Flow, start, listen, or_, and_

fired = []

class TriggerFlow(Flow):
    @start()
    def fast(self):
        fired.append("fast")
        return "fast-done"

    @start()
    def slow(self):
        fired.append("slow")
        return "slow-done"

    # or_: run as soon as ANY listed trigger completes
    @listen(or_(fast, slow))
    def on_any(self, payload):
        fired.append(f"on_any<-{payload}")

    # and_: run only after ALL listed triggers have completed
    @listen(and_(fast, slow))
    def on_all(self, payload):
        fired.append("on_all")

TriggerFlow().kickoff()
print("execution order:")
for i, step in enumerate(fired, 1):
    print(f"  {i}. {step}")
print(f"\non_any fired {sum(s.startswith('on_any') for s in fired)} time(s)")
print(f"on_all fired {sum(s == 'on_all' for s in fired)} time(s)")

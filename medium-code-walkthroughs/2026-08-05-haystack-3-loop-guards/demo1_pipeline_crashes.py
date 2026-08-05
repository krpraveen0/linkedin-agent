"""demo1: a Haystack Pipeline loop with no exit route CRASHES.

When a component in a cycle is scheduled more times than
`max_runs_per_component`, the Pipeline raises PipelineMaxComponentRuns.

Run:  python demo1_pipeline_crashes.py
"""
from haystack import component, Pipeline
from haystack.components.joiners import BranchJoiner
from haystack.core.errors import PipelineMaxComponentRuns

worker_runs = []


@component
class Worker:
    """Stands in for an agent step that never signals 'done' -- it always
    hands its output straight back into the loop."""

    @component.output_types(value=int)
    def run(self, value: int):
        worker_runs.append(value)
        return {"value": value + 1}


pipe = Pipeline(max_runs_per_component=3)
# BranchJoiner merges the initial input and the loop-back input into one socket,
# which is how Haystack lets you build a cycle at all.
pipe.add_component("loop", BranchJoiner(int))
pipe.add_component("worker", Worker())
pipe.connect("loop.value", "worker.value")
pipe.connect("worker.value", "loop.value")  # feed the result back in forever

try:
    pipe.run({"loop": {"value": 0}})
    print("finished normally (this should not happen)")
except PipelineMaxComponentRuns as e:
    print(f"RAISED {type(e).__name__}: {e}")

print(f"Worker.run executed {len(worker_runs)} times; values seen: {worker_runs}")

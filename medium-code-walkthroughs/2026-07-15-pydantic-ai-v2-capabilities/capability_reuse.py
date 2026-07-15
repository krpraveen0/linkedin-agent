"""A capability is a portable unit: define once, plug into many agents.

Same `audit_cap` object, two unrelated agents, one shared counter.
"""
from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.models.test import TestModel

calls = {"n": 0}


def count_requests(ctx, request_context):
    calls["n"] += 1
    return request_context


# One capability object...
audit_cap = Hooks(before_model_request=count_requests, id="audit")

# ...reused across two independent agents. TestModel just echoes a canned reply.
translator = Agent(TestModel(custom_output_text="bonjour"), capabilities=[audit_cap])
summarizer = Agent(TestModel(custom_output_text="tl;dr"), capabilities=[audit_cap])

print("translator output:", translator.run_sync("Translate hello to French").output)
print("summarizer output:", summarizer.run_sync("Summarize this document").output)
print("total model requests counted by the one shared capability:", calls["n"])

"""Instrument a tiny, LLM-free agent with OpenTelemetry using the GenAI
semantic-convention attribute names, then print the finished span tree.

No network, no API key: an in-memory exporter captures the spans and we render
them ourselves so the output is deterministic (timestamps omitted on purpose).
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

# The real GenAI convention constants shipped in the installed package.
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_AGENT_NAME,
    GEN_AI_TOOL_NAME,
    GEN_AI_TOOL_CALL_ARGUMENTS,
    GEN_AI_TOOL_CALL_RESULT,
    GenAiOperationNameValues,
)

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("demo.agent")

AGENT_NAME = "unit-converter"

# Two plain-Python "tools". No model in the loop — the point is the span shape.
def to_celsius(f):
    return round((f - 32) * 5 / 9, 2)

def to_miles(km):
    return round(km * 0.621371, 2)

TOOLS = {"to_celsius": to_celsius, "to_miles": to_miles}


def run_tool(name, arg):
    # execute_tool span: name = "execute_tool {gen_ai.tool.name}", tool.name Required.
    with tracer.start_as_current_span(f"execute_tool {name}") as span:
        span.set_attribute(GEN_AI_OPERATION_NAME,
                           GenAiOperationNameValues.EXECUTE_TOOL.value)
        span.set_attribute(GEN_AI_TOOL_NAME, name)
        span.set_attribute(GEN_AI_TOOL_CALL_ARGUMENTS, str(arg))
        result = TOOLS[name](arg)
        span.set_attribute(GEN_AI_TOOL_CALL_RESULT, str(result))
        return result


def invoke_agent(plan):
    # invoke_agent span: name = "invoke_agent {gen_ai.agent.name}".
    with tracer.start_as_current_span(f"invoke_agent {AGENT_NAME}") as span:
        span.set_attribute(GEN_AI_OPERATION_NAME,
                           GenAiOperationNameValues.INVOKE_AGENT.value)
        span.set_attribute(GEN_AI_PROVIDER_NAME, "local")
        span.set_attribute(GEN_AI_AGENT_NAME, AGENT_NAME)
        return [run_tool(name, arg) for name, arg in plan]


results = invoke_agent([("to_celsius", 98.6), ("to_miles", 42.0)])

# Render the captured spans as a parent/child tree.
spans = exporter.get_finished_spans()
by_id = {s.context.span_id: s for s in spans}
children = {}
for s in spans:
    parent = s.parent.span_id if s.parent else None
    children.setdefault(parent, []).append(s)

def show(span_id, depth=0):
    for s in children.get(span_id, []):
        op = s.attributes.get(GEN_AI_OPERATION_NAME)
        print("  " * depth + f"- {s.name}   [{op}]")
        for k in (GEN_AI_TOOL_NAME, GEN_AI_TOOL_CALL_ARGUMENTS,
                  GEN_AI_TOOL_CALL_RESULT):
            if k in s.attributes:
                print("  " * depth + f"    {k} = {s.attributes[k]}")
        show(s.context.span_id, depth + 1)

print("agent results:", results)
print("span tree (root -> children):")
show(None)

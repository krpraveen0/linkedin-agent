"""Inspect the installed GenAI convention module to see what the July 16, 2026
release (opentelemetry-semantic-conventions 0.65b0) actually did to the
gen_ai.* namespace, rather than trusting a blog post.
"""
import inspect
from importlib.metadata import version
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as g
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GenAiOperationNameValues,
)

print("opentelemetry-semantic-conventions:",
      version("opentelemetry-semantic-conventions"))

src = inspect.getsource(g)
constants = [n for n in dir(g) if n.startswith("GEN_AI_") and n.isupper()]

moved = [n for n in constants
         if f'{n}: Final' in src
         and "semantic-conventions-genai" in src.split(f"{n}: Final", 1)[1][:400]]

print(f"gen_ai.* string constants in module: {len(constants)}")
print(f"...carrying a 'moved to semantic-conventions-genai' deprecation note: "
      f"{len(moved)}")

# The specific migration every existing instrumentation has to make.
i = src.find("GEN_AI_SYSTEM: Final")
note = src[i:i + 400].split('"""')[1].strip().replace("\n", " ")
print("\ngen_ai.system ->", note)

print("\nAgent operation names still importable (values unchanged):")
for name in ("CREATE_AGENT", "INVOKE_AGENT", "EXECUTE_TOOL"):
    print(f"  {name} = {getattr(GenAiOperationNameValues, name).value!r}")

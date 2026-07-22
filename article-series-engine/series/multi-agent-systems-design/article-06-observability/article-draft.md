# Observability and evaluation for multi-agent systems: what to actually measure

*Most observability content for multi-agent systems is either an academic benchmark paper or a vendor-platform pitch with a demo button at the bottom. This article is neither - a minimal-viable observability stack you can actually build, grounded in the real standard the industry is converging on, not a product.*

## The standard that already exists, underused

OpenTelemetry's GenAI Special Interest Group has been standardizing exactly this problem since April 2024: a vendor-neutral schema of `gen_ai.*` attributes and span names for LLM calls, agent invocations, and tool executions, so telemetry stays consistent whether the underlying model is Claude, GPT, or Gemini. OpenTelemetry itself graduated to full CNCF status in May 2026. The GenAI conventions specifically are still marked "Development" as of this writing, but the core shape is stable enough to build against: an `invoke_agent` span at the top of each agent's work, `execute_tool` spans for each tool call underneath it, and metrics like `gen_ai.client.operation.duration` and `gen_ai.client.token.usage` tracked per call.

Most teams building multi-agent systems either skip this entirely and rely on scattered `print` statements, or jump straight to a commercial observability platform before establishing what they actually need to trace. Neither is necessary. The minimal version - four checks, described below - runs without adopting a platform, and maps directly onto the vendor-neutral conventions above.

The conventions cover four primary areas as of early 2026: LLM client spans (individual calls to a model provider), agent spans (`create_agent`, `invoke_agent`), events (structured capture of prompt and completion content, with real privacy tradeoffs covered later in this article), and metrics (`gen_ai.client.operation.duration`, `gen_ai.client.token.usage`). Because the spec is still marked "Development," attribute names can shift between versions - the `OTEL_SEMCONV_STABILITY_OPT_IN` environment variable exists specifically so instrumentation can emit both old and new attribute names during that transition, rather than breaking dashboards built against last quarter's naming. Worth knowing that variable exists before assuming a naming change in the spec means starting your instrumentation over.

<image src="file-upload://3a5c633a-e23a-8101-8b4c-00b204dad63a"></image>

*The exact failure this article is built around: DevPulse's own architecture breaks trace propagation at the one hop that was never a direct function call.*

## The failure this article is actually about

Articles 02, 04, and 05 have all now examined the classifier-to-provisioner relationship - a blackboard, a trust boundary, a spec-and-handoff-and-verification pipeline. None of them asked whether the relationship can even be observed end to end.

Here is why that question is not automatic. A direct function call or an HTTP request propagates trace context for free - the caller's trace ID travels with the call, and most instrumentation libraries handle this without anyone writing code for it. DevPulse's classifier-to-provisioner handoff is not a direct call. It is a write to a shared filesystem, read later by a different process. Nothing propagates a trace ID across that gap automatically, because there is no call for it to ride along on. If the classifier does not deliberately write its trace ID into the spec file, and the provisioner does not deliberately read it back out, the two halves of one real task become two disconnected traces, correlated only by hoping their timestamps line up.

This is not a hypothetical. It is the direct, predictable consequence of Article 02's own finding: the moment a relationship is a blackboard instead of a call, everything that used to happen for free - including trace propagation - has to be designed in deliberately instead.

## Four checks, not a platform

`minimal_observability_harness.py`, in this folder's `src/`, implements all four.

**Trace connectivity**, first. Given a set of spans for one real task, do they all share one trace ID?

```python
connected_spans = [
    Span(trace_id="abc123", span_id="s1", parent_span_id=None, name="invoke_agent:supervisor", duration_ms=150),
    Span(trace_id="abc123", span_id="s2", parent_span_id="s1", name="execute_tool:classify", duration_ms=900),
    # provisioner reads trace_id="abc123" back out of the spec file itself
    Span(trace_id="abc123", span_id="s3", parent_span_id="s2", name="execute_tool:provision", duration_ms=5200),
]
check_trace_connected(connected_spans)
# -> (True, "all 3 spans share one trace_id - full story reconstructable from one ID")
```

Now the broken version - the spec file never carried a trace ID, so the provisioner starts its own:

```python
broken_spans = [
    Span(trace_id="xyz789", span_id="s1", parent_span_id=None, name="invoke_agent:supervisor", duration_ms=150),
    Span(trace_id="xyz789", span_id="s2", parent_span_id="s1", name="execute_tool:classify", duration_ms=900),
    Span(trace_id="def456", span_id="s1", parent_span_id=None, name="execute_tool:provision", duration_ms=5200),
]
check_trace_connected(broken_spans)
# -> (False, "spans are split across 2 disconnected traces: {'def456', 'xyz789'}")
```

Same underlying task. The only difference is one deliberate design decision: does the spec file carry a trace ID or not. Everything downstream of that single decision - whether a compliance question about this specific task can be answered from one trace or requires manually correlating two unrelated-looking ones - depends on it.

**Latency budget**, second, broken down per span rather than checked only in total. DevPulse's own stated target for provisioning a workspace from intent is 8 seconds end to end. Checking only the total hides which specific step is responsible when that number creeps up:

```python
DEVPULSE_BUDGET_MS = {
    "invoke_agent:supervisor": 200,
    "execute_tool:classify": 1000,
    "execute_tool:provision": 6000,
}
check_latency_budget(connected_spans, DEVPULSE_BUDGET_MS)
# -> [] (no violations - total 6250ms, under the 8000ms budget)
```

A per-span budget catches a regression at the step that caused it. A total-only budget just tells you the system got slower, days after a specific step started taking longer and nobody noticed which one.

**Token budget**, third, using the same logic applied to cost instead of time:

```python
usages = [
    TokenUsage(span_name="execute_tool:classify", input_tokens=800, output_tokens=150),
    TokenUsage(span_name="execute_tool:provision", input_tokens=1200, output_tokens=400),
]
token_budget = {"execute_tool:classify": 1200, "execute_tool:provision": 1500}
check_token_budget(usages, token_budget)
# -> ["execute_tool:provision used 1600 tokens, budget was 1500"]
```

This catches exactly the kind of drift that a monthly bill only reveals after the fact - one specific step's token spend crept past its stated budget, flagged at the step itself rather than discovered as a surprising total three weeks later.

**Tool-selection accuracy**, fourth, the actual eval harness rather than a latency or cost check. This is where "lightweight" earns its meaning: not a benchmark suite, just a small set of test cases run against the agent's real selection logic.

```python
def naive_tool_selector(task_description: str) -> str:
    if "project" in task_description.lower():
        return "provision"
    return "classify"

test_cases = [
    ToolSelectionCase("sort this downloaded spec into the right project folder", "classify"),
    ToolSelectionCase("set up the workspace for this project", "provision"),
    ToolSelectionCase("file this PDF under the correct project", "classify"),
]
eval_tool_selection_accuracy(test_cases, naive_tool_selector)
# -> (0.33, ["'sort this downloaded spec...': expected classify, got provision", ...])
```

Thirty-three percent, on three genuinely simple cases, because the naive selector keyed off the word "project" rather than the actual intended action. This is a deliberately naive example, but the shape of the failure is exactly the kind that survives unnoticed in a real system for a long time: the selector works on the training examples someone happened to test with, and silently picks the wrong tool the moment a real task's phrasing looks slightly different.

## Why not just adopt a platform

Commercial observability platforms for LLM systems are a real, legitimate option, and most of them build on exactly the OpenTelemetry conventions described above rather than inventing a proprietary schema - which is worth knowing before evaluating one, since a platform that ignores the emerging standard is a worse bet than one that extends it. But adopting a platform is an organizational decision with real cost and real lock-in, and it is not a prerequisite for the four checks in this article. A team that cannot yet justify that decision can still have trace connectivity, per-span latency and token budgets, and a tool-selection eval today, in a file small enough to read in one sitting, and add a platform later without throwing any of it away - since the underlying span structure is the same either way.

One thing worth deciding deliberately rather than by default: whether prompt and completion content gets captured on the spans themselves. The emerging convention recognizes three real options - do not capture content at all, capture it directly on the span, or store it externally and keep only a reference on the span. For a system touching anything like DevPulse's inbox contents, capturing raw message text directly onto a long-lived trace is a real, avoidable privacy exposure, not a hypothetical one. The third option - external storage plus a pointer - is the one that scales without turning your trace store into an unintended copy of every email the inbox agent ever read.

## What this looks like Monday morning

Pick the one relationship in your own system most likely to have a broken trace, the same way Article 04 asked you to find the one relationship most likely to be a confused deputy. It is almost always the same kind of relationship: wherever control flow crosses a boundary that is not a direct call - a shared file, a queue, a webhook, anything asynchronous - trace context has to be carried deliberately, and it is exactly the kind of detail that works in a demo and silently stops working the day someone refactors the handoff mechanism without knowing propagation depended on it.

Set a per-span budget, in both time and tokens, before you need one, not after a user complains the system feels slow or a bill arrives with a number nobody expected. A number written down in advance is a check. A number estimated after the fact from a complaint is a guess dressed up as an incident report.

Run three real test cases through your own tool-selection logic this week, not next quarter. If a selector this simple can fail two out of three, worth finding out now which of your own agents has never actually been checked against anything harder than the one example that happened to work in the demo.

The next article in this series picks up from here: everything so far has assumed one system's internal relationships. The next question is what happens when two of your own agents compete for the same external resource at the same time - shared-resource contention.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. Multi-agent or overkill? A decision framework before you add a second agent — not yet published
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. The four canonical orchestration patterns, and how to actually choose one — not yet published
4. Designing the trust boundary: authorization between agents that isn't an afterthought — not yet published
5. Preventing the MAST failure modes by design, not by autopsy — not yet published
6. **Observability and evaluation for multi-agent systems: what to actually measure** *(this article)*
7. Shared-resource contention: when your agents fight over the same database row — not yet published
8. Putting it together: designing a production multi-agent system end to end — not yet published

## References

1. Semantic Conventions for Generative AI Systems, OpenTelemetry
   https://opentelemetry.io/docs/specs/semconv/gen-ai/
2. Inside the LLM Call: GenAI Observability with OpenTelemetry, OpenTelemetry Blog
   https://opentelemetry.io/blog/2026/genai-observability/

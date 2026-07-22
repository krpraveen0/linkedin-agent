"""
minimal_observability_harness.py

A small, runnable tool for Article 06 ("Observability and evaluation for
multi-agent systems: what to actually measure").

Follows OpenTelemetry's GenAI semantic conventions in spirit
(invoke_agent / execute_tool span names, trace_id/parent_span_id
propagation - see https://opentelemetry.io/docs/specs/semconv/gen-ai/)
without requiring a full OTel SDK or a third-party observability
platform. Two checks, both aimed at the specific failure this article
argues is easy to miss:

1. Trace connectivity - do all spans for one real task share a single
   trace_id, or did context get lost at a hop (like DevPulse's
   classifier-to-provisioner handoff, which crosses a shared filesystem
   rather than a direct function call)?
2. Latency budget - does each span fit inside a stated budget, so a
   regression is caught at the specific step that caused it, not just
   noticed as "the whole thing got slower"?

Usage:
    python minimal_observability_harness.py
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    duration_ms: float


def check_trace_connected(spans: list[Span]) -> tuple[bool, str]:
    trace_ids = {s.trace_id for s in spans}
    if len(trace_ids) == 1:
        return True, f"all {len(spans)} spans share one trace_id - full story reconstructable from one ID"
    return False, f"spans are split across {len(trace_ids)} disconnected traces: {trace_ids}"


def check_latency_budget(spans: list[Span], budget_ms: dict[str, float]) -> list[str]:
    violations = []
    for s in spans:
        limit = budget_ms.get(s.name)
        if limit is not None and s.duration_ms > limit:
            violations.append(f"{s.name} took {s.duration_ms:.0f}ms, budget was {limit:.0f}ms")
    return violations


# --- Cost budget: same idea as latency, applied to token spend ---

@dataclass(frozen=True)
class TokenUsage:
    span_name: str
    input_tokens: int
    output_tokens: int


def check_token_budget(usages: list[TokenUsage], budget_tokens: dict[str, int]) -> list[str]:
    violations = []
    for u in usages:
        limit = budget_tokens.get(u.span_name)
        total = u.input_tokens + u.output_tokens
        if limit is not None and total > limit:
            violations.append(f"{u.span_name} used {total} tokens, budget was {limit}")
    return violations


# --- Tool-selection accuracy: a lightweight eval harness, not a platform ---

@dataclass(frozen=True)
class ToolSelectionCase:
    task_description: str
    expected_tool: str


def eval_tool_selection_accuracy(
    cases: list[ToolSelectionCase], select_tool_fn
) -> tuple[float, list[str]]:
    """Runs each test case through the agent's actual tool-selection
    function and reports accuracy - the concrete, minimal-viable version
    of an eval harness, not a benchmark suite or a platform subscription."""
    failures = []
    correct = 0
    for case in cases:
        actual = select_tool_fn(case.task_description)
        if actual == case.expected_tool:
            correct += 1
        else:
            failures.append(f"{case.task_description!r}: expected {case.expected_tool}, got {actual}")
    accuracy = correct / len(cases) if cases else 0.0
    return accuracy, failures


# DevPulse's stated target for Scenario B: intent to fully-provisioned
# desktop in 8 seconds. Broken down per span, not just checked in total.
DEVPULSE_BUDGET_MS = {
    "invoke_agent:supervisor": 200,
    "execute_tool:classify": 1000,
    "execute_tool:provision": 6000,
}


if __name__ == "__main__":
    print("--- Scenario A: trace context correctly propagated through the spec file ---")
    connected_spans = [
        Span(trace_id="abc123", span_id="s1", parent_span_id=None, name="invoke_agent:supervisor", duration_ms=150),
        Span(trace_id="abc123", span_id="s2", parent_span_id="s1", name="execute_tool:classify", duration_ms=900),
        # provisioner reads trace_id="abc123" back out of the spec file itself
        Span(trace_id="abc123", span_id="s3", parent_span_id="s2", name="execute_tool:provision", duration_ms=5200),
    ]
    ok, msg = check_trace_connected(connected_spans)
    print(f"  connectivity check: {ok} - {msg}")
    violations = check_latency_budget(connected_spans, DEVPULSE_BUDGET_MS)
    total_ms = sum(s.duration_ms for s in connected_spans)
    print(f"  total latency: {total_ms:.0f}ms against an 8000ms budget")
    print(f"  budget violations: {violations if violations else 'none'}\n")

    print("--- Scenario B: the spec file never carried a trace_id ---")
    broken_spans = [
        Span(trace_id="xyz789", span_id="s1", parent_span_id=None, name="invoke_agent:supervisor", duration_ms=150),
        Span(trace_id="xyz789", span_id="s2", parent_span_id="s1", name="execute_tool:classify", duration_ms=900),
        # provisioner had nothing to read, so it starts its own trace
        Span(trace_id="def456", span_id="s1", parent_span_id=None, name="execute_tool:provision", duration_ms=5200),
    ]
    ok, msg = check_trace_connected(broken_spans)
    print(f"  connectivity check: {ok} - {msg}")
    print("  a compliance question about this task now has to manually")
    print("  correlate two unrelated-looking traces by timestamp guessing,")
    print("  instead of pulling one trace_id.\n")

    print("--- Token/cost budget, same idea as latency ---")
    usages = [
        TokenUsage(span_name="execute_tool:classify", input_tokens=800, output_tokens=150),
        TokenUsage(span_name="execute_tool:provision", input_tokens=1200, output_tokens=400),
    ]
    token_budget = {"execute_tool:classify": 1200, "execute_tool:provision": 1500}
    violations = check_token_budget(usages, token_budget)
    print(f"  token budget violations: {violations if violations else 'none'}\n")

    print("--- Tool-selection accuracy: the lightweight eval harness ---")

    def naive_tool_selector(task_description: str) -> str:
        # Deliberately naive - picks "provision" for anything mentioning a
        # project, even when classification is what was actually needed.
        if "project" in task_description.lower():
            return "provision"
        return "classify"

    test_cases = [
        ToolSelectionCase("sort this downloaded spec into the right project folder", "classify"),
        ToolSelectionCase("set up the workspace for this project", "provision"),
        ToolSelectionCase("file this PDF under the correct project", "classify"),
    ]
    accuracy, failures = eval_tool_selection_accuracy(test_cases, naive_tool_selector)
    print(f"  accuracy: {accuracy:.0%}")
    print(f"  failures: {failures}")

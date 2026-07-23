"""
Two things that go wrong with tool use in real systems, both directly
named in Anthropic's own tool-use documentation - a hallucinated tool
call, and malformed arguments. This shows both, and what "handling it
right" actually looks like versus what happens if you don't.
"""

import sys
sys.path.insert(0, ".")
from tool_use import ToolUseBlock, execute_tool_call, TOOL_SCHEMA


def naive_execute_tool_call(block: ToolUseBlock):
    """The version with NO validation - just trusts the model's
    tool_use block completely and runs it."""
    if block.name == "check_ticket_status":
        from tool_use import check_ticket_status
        return check_ticket_status(**block.input)
    # no else branch - a hallucinated tool name just... falls through
    # silently, or crashes, depending on what comes next in a real system


if __name__ == "__main__":
    print("Case 1: a hallucinated tool name")
    print("(the real docs note this happens more when tool schemas overlap")
    print("or the request is ambiguous - it's rare, but it's real)\n")

    hallucinated_call = ToolUseBlock(name="check_ticket_stauts", input={"ticket_id": "TICKET-123"})
    # notice the typo in the tool name - "stauts" instead of "status" -
    # this is exactly the shape a real hallucinated call takes

    print("  With validation (execute_tool_call from tool_use.py):")
    result = execute_tool_call(hallucinated_call)
    print(f"    {result}")
    print("    -> the model gets an informative error back and can retry\n")

    print("  Without validation (naive_execute_tool_call):")
    result = naive_execute_tool_call(hallucinated_call)
    print(f"    returned: {result!r}")
    print("    -> no exception, no error, nothing. It silently returns None,")
    print("       as if the call simply succeeded with no result. That's")
    print("       arguably worse than a crash - nothing signals anything")
    print("       went wrong, to your code or to the model.\n")

    print("Case 2: malformed arguments (missing the required field)")
    malformed_call = ToolUseBlock(name="check_ticket_status", input={})
    print("  With validation:")
    result = execute_tool_call(malformed_call)
    print(f"    {result}")

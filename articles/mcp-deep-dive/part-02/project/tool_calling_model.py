"""Stand-in for a customized tool-calling model hosted on a serverless
Amazon SageMaker AI endpoint.

The article this project accompanies (../article.md) is about hosting a
small model *fine-tuned specifically for one MCP tool schema* on a
SageMaker AI serverless/on-demand endpoint, so an agent only pays for
inference during a burst of tool-calling turns instead of running a GPU
instance around the clock. Actually deploying and invoking a SageMaker
endpoint needs an AWS account, IAM role, and billable GPU/Inferentia
capacity, none of which are available in this repository's CI sandbox --
so per aep/prompts/production-engineering.md ("never claim execution
without evidence"), this module is an explicit, clearly-labeled
deterministic stand-in for that hosted model's decision step, not a call
to SageMaker. It reproduces the *shape* of what the customized model
returns -- a tool name plus JSON-Schema-valid arguments, matching the
`tools/list` schema the MCP server advertised -- so the rest of the agent
loop (mcp_agent.py) is identical to what it would be against a real
endpoint; only this function would change.
"""
import re


def decide_tool_call(user_message: str, tools: list) -> dict | None:
    """Return {'name': ..., 'arguments': {...}} or None if no tool applies.

    A real customized model picks this from the schemas in `tools` via a
    learned forward pass; this rule-based version picks it via regex so the
    demo has no model-weights dependency.
    """
    tool_names = {t["name"] for t in tools}

    order_match = re.search(r"\border\s+([A-Za-z0-9]+)", user_message, re.IGNORECASE)
    if order_match and "get_order_status" in tool_names:
        return {"name": "get_order_status", "arguments": {"order_id": order_match.group(1).upper()}}

    convert_match = re.search(
        r"([\d.]+)\s*([A-Za-z]{3})\s+(?:to|in)\s+([A-Za-z]{3})", user_message, re.IGNORECASE
    )
    if convert_match and "convert_currency" in tool_names:
        amount, from_ccy, to_ccy = convert_match.groups()
        return {
            "name": "convert_currency",
            "arguments": {"amount": float(amount), "from_currency": from_ccy, "to_currency": to_ccy},
        }

    return None

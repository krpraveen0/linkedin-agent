"""
tool_use.py

Article 03: the actual mechanism behind "agents can call APIs, run
code, search the web" - modeled on Claude's real tool_use/tool_result
shape (see the article's References), without needing an API key.

The pattern, for real: the model returns a tool_use block (a tool name
plus a JSON object of arguments). YOUR code executes it - the model
never runs anything itself. You send the result back in a tool_result
block. That round trip is what this file builds, with a deterministic
stand-in for the "which tool, which arguments" decision.
"""

from dataclasses import dataclass
from typing import Any


# --- Step 1: define a tool, the way a real schema would ---

TOOL_SCHEMA = {
    "name": "check_ticket_status",
    "description": "Look up the current status of a support ticket by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "e.g. 'TICKET-123'"},
        },
        "required": ["ticket_id"],
    },
}

# The actual data the tool reads - a stand-in for a real database
TICKET_DATABASE = {
    "TICKET-123": "open",
    "TICKET-456": "resolved",
}


# --- Step 2: the real tool - a plain function, nothing agent-specific about it ---

def check_ticket_status(ticket_id: str) -> str:
    if ticket_id not in TICKET_DATABASE:
        raise KeyError(f"no such ticket: {ticket_id}")
    return TICKET_DATABASE[ticket_id]


# --- Step 3: the tool_use block - what a real model response looks like ---

@dataclass(frozen=True)
class ToolUseBlock:
    """Shaped like Claude's actual tool_use content block: a name and a
    dict of arguments. In a real API call this comes back inside the
    response. Here, decide_tool_call is standing in for that."""
    name: str
    input: dict[str, Any]


def decide_tool_call(user_message: str) -> ToolUseBlock:
    """Deterministic stand-in for the model's decision. A real model
    reads the schema and the conversation and decides this same shape -
    which tool, with what arguments."""
    if "TICKET-" in user_message:
        raw = user_message.split("TICKET-")[1].split()[0]
        ticket_id = "TICKET-" + "".join(ch for ch in raw if ch.isalnum())
        return ToolUseBlock(name="check_ticket_status", input={"ticket_id": ticket_id})
    raise ValueError("no ticket ID found in message")


# --- Step 4: the tool_result block - what goes back to the model ---

@dataclass(frozen=True)
class ToolResultBlock:
    """Shaped like Claude's actual tool_result block: the content
    (as a string) and an is_error flag, exactly as the real docs
    recommend - a clear message, not a bare 'failed'."""
    content: str
    is_error: bool = False


def execute_tool_call(block: ToolUseBlock) -> ToolResultBlock:
    """Your application's job, not the model's. The model never runs
    check_ticket_status - it only ever sees this function's return
    value, packaged as a tool_result."""
    if block.name != TOOL_SCHEMA["name"]:
        return ToolResultBlock(
            content=f"Error: unknown tool '{block.name}' - not in the available tool list",
            is_error=True,
        )
    try:
        status = check_ticket_status(**block.input)
        return ToolResultBlock(content=f"Ticket status: {status}")
    except KeyError as e:
        return ToolResultBlock(content=f"Error: {e}", is_error=True)
    except TypeError as e:
        return ToolResultBlock(content=f"Error: malformed arguments - {e}", is_error=True)


if __name__ == "__main__":
    print("A real, working round trip:")
    tool_call = decide_tool_call("What's the status of TICKET-123?")
    print(f"  model requested: {tool_call}")
    result = execute_tool_call(tool_call)
    print(f"  tool_result: {result}")

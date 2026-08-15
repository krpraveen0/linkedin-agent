"""What Instructor actually sends the model, per Mode. No API key, no network.

We call instructor's own request-building function, handle_response_model,
with the SAME Pydantic model and different Modes, and print the request it
hands to the provider client. This is the real code path a patched client
uses -- we just stop before the HTTP call.
"""
import json
from pydantic import BaseModel, Field
from instructor import Mode
from instructor.processing.response import handle_response_model


class User(BaseModel):
    name: str = Field(description="The person's full name")
    age: int


def build(mode: Mode) -> dict:
    # returns the kwargs instructor would pass to the provider's chat call
    _, kwargs = handle_response_model(
        User, mode=mode,
        messages=[{"role": "user", "content": "Extract: Jane Doe is 30"}],
    )
    return kwargs


print("Instructor exposes", len([m for m in Mode]), "modes.\n")

for mode in (Mode.TOOLS, Mode.JSON, Mode.MD_JSON):
    kw = build(mode)
    print("=" * 64)
    print("Mode:", mode.value)
    print("  tools sent?          ", "tools" in kw)
    print("  tool_choice forced?  ", kw.get("tool_choice", "no"))
    print("  response_format:     ", kw.get("response_format", "none"))
    print("  # messages:          ", len(kw["messages"]),
          "(started with 1)")

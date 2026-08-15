"""TOOLS vs TOOLS_STRICT, at the request-building layer."""
import json
from pydantic import BaseModel
from instructor import Mode
from instructor.processing.response import handle_response_model


class User(BaseModel):
    name: str
    age: int


def req(mode):
    _, kw = handle_response_model(
        User, mode=mode,
        messages=[{"role": "user", "content": "x"}],
    )
    return json.dumps(kw, sort_keys=True, default=str)


tools = req(Mode.TOOLS)
strict = req(Mode.TOOLS_STRICT)
print("TOOLS request == TOOLS_STRICT request?", tools == strict)
print("'strict' anywhere in the request?     ", "strict" in tools)

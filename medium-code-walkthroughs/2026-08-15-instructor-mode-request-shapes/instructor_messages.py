"""Where did the schema go? For JSON/MD_JSON, into the prompt itself."""
from pydantic import BaseModel, Field
from instructor import Mode
from instructor.processing.response import handle_response_model


class User(BaseModel):
    name: str = Field(description="The person's full name")
    age: int


_, kw = handle_response_model(
    User, mode=Mode.MD_JSON,
    messages=[{"role": "user", "content": "Extract: Jane Doe is 30"}],
)

for m in kw["messages"]:
    print(f"[{m['role']}]")
    print(m["content"].strip())
    print()

# The tool-call path names the tool after your class and writes its own
# description when the model has no docstring:
_, kwt = handle_response_model(
    User, mode=Mode.TOOLS,
    messages=[{"role": "user", "content": "x"}],
)
fn = kwt["tools"][0]["function"]
print("tool name:       ", fn["name"])
print("tool description:", repr(fn["description"]))

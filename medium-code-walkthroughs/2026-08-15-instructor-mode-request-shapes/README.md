# What Instructor actually sends the model, per Mode

Companion code for the Medium article *"I Gave Instructor One Pydantic Model. Its Mode Setting Sent My LLM Three Different Requests."* (2026-08-15).

These scripts call Instructor's own request-building function, `handle_response_model`, with the **same** Pydantic model and different `Mode` values, then print the request Instructor would hand the provider client. No API key and no network call — the code path stops one step before the HTTP request.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install "instructor==1.15.4"   # pulls pydantic 2.13.x, openai 2.54.x
```

Verified environment: Python 3.11, `instructor==1.15.4`, `pydantic==2.13.4`, `openai==2.54.0`.

## Run

```bash
python instructor_modes.py      # 3 modes -> 3 request shapes
python instructor_messages.py   # where the schema goes for MD_JSON; auto tool name/description
python instructor_strict.py     # TOOLS vs TOOLS_STRICT at the request-building layer
```

## Real captured output

### `instructor_modes.py`

```
Instructor exposes 38 modes.

================================================================
Mode: tool_call
  tools sent?           True
  tool_choice forced?   {'type': 'function', 'function': {'name': 'User'}}
  response_format:      none
  # messages:           1 (started with 1)
================================================================
Mode: json_mode
  tools sent?           False
  tool_choice forced?   no
  response_format:      {'type': 'json_object'}
  # messages:           2 (started with 1)
================================================================
Mode: markdown_json_mode
  tools sent?           False
  tool_choice forced?   no
  response_format:      none
  # messages:           2 (started with 1)
```

### `instructor_messages.py`

The outer fence below is four backticks so the model-facing triple-backtick instruction renders literally.

````text
[system]
As a genius expert, your task is to understand the content and provide
            the parsed objects in json that match the following json_schema:


            {
  "properties": {
    "name": {
      "description": "The person's full name",
      "title": "Name",
      "type": "string"
    },
    "age": {
      "title": "Age",
      "type": "integer"
    }
  },
  "required": [
    "name",
    "age"
  ],
  "title": "User",
  "type": "object"
}

            Make sure to return an instance of the JSON, not the schema itself

[user]
Extract: Jane Doe is 30

Return the correct JSON response within a ```json codeblock. not the JSON_SCHEMA

tool name:        User
tool description: 'Correctly extracted `User` with all the required parameters with correct types'
````

### `instructor_strict.py`

```
TOOLS request == TOOLS_STRICT request? True
'strict' anywhere in the request?      False
```

## Notes

- The exact injected strings and the mode count (38) are tied to `instructor==1.15.4`. Pin the version to reproduce byte-for-byte.
- As of the 1.15.x line, Instructor's public modules are compatibility facades over a rewritten, provider-owned `v2/` core; the mode-to-request mapping is dispatched per provider through a registry.

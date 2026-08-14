# transformers builds your tool schema from the docstring

Code for the Medium article **"I Passed transformers a Python Function as a Tool. It Read My Docstring to Decide What the Model Sees."** (2026-08-14).

In Transformers 5.x, when you pass a plain Python function to
`apply_chat_template(tools=[fn])`, the library calls `get_json_schema(fn)` to
build the OpenAI-style tool schema from the function's **docstring and type
hints**. This walkthrough demonstrates that conversion, the required/optional
behavior, the validation errors for underdocumented functions, and the final
prompt-injection step — all on CPU with no model weights.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install "transformers==5.15.0" jinja2
```

`torch` is not required; the chat-template utilities work without it (you will
see a one-line stderr notice from Transformers saying so).

## Run

```bash
python walkthrough.py
```

## Real captured output

Captured on 2026-08-14 with transformers 5.15.0, Python 3.11. The first line is
a stderr warning from Transformers, expected when torch is not installed.

```
[transformers] PyTorch was not found. Models won't be available and only tokenizers, configuration and file/data utilities can be used.

==== 1. docstring + type hints -> JSON schema ====
{
  "type": "function",
  "function": {
    "name": "get_current_temperature",
    "description": "Get the current temperature at a location.",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "The location to get the temperature for, in the format \"City, Country\""
        },
        "unit": {
          "type": "string",
          "enum": [
            "celsius",
            "fahrenheit"
          ],
          "description": "The unit to return the temperature in."
        }
      },
      "required": [
        "location",
        "unit"
      ]
    },
    "return": {
      "type": "number",
      "description": "The current temperature at the specified location in the specified units, as a float."
    }
  }
}

==== 2. defaults drop from 'required'; Optional -> nullable ====
required: ['query']
limit   : {"type": "integer", "description": "Max number of results to return."}
category: {"type": "string", "nullable": true, "description": "Restrict results to one category."}

==== 3. what gets rejected ====
missing_arg_doc: DocstringParsingException: Cannot generate JSON schema for missing_arg_doc because the docstring has no description for the argument 'unit'
missing_type_hint: TypeHintParsingException: Argument location is missing a type hint in function missing_type_hint
no_docstring: DocstringParsingException: Cannot generate JSON schema for no_docstring because it has no docstring!

==== 4. the schema is injected into the prompt the model reads ====
You can call these tools:
- get_current_temperature: Get the current temperature at a location.
  args: ['location', 'unit']
<|user|> What's it like in Paris?
```

## Sources

- [Transformers v5.0.0 release (Jan 26, 2026)](https://github.com/huggingface/transformers/releases/tag/v5.0.0)
- [transformers on PyPI (5.15.0, Aug 10, 2026)](https://pypi.org/project/transformers/)
- [`chat_template_utils.py` source](https://github.com/huggingface/transformers/blob/main/src/transformers/utils/chat_template_utils.py)

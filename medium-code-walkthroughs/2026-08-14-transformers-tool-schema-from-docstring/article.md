# I Passed transformers a Python Function as a Tool. It Read My Docstring to Decide What the Model Sees.

I gave a local model one tool: a Python function called `get_current_temperature`. I never wrote a JSON schema for it. I never described its parameters in a config file. I just handed the function object to `apply_chat_template(tools=[...])` and moved on.

Then I printed the prompt that actually reached the model. The description of my tool was a sentence I had written in the function's docstring. The list of valid units the model was allowed to pass came from a `(choices: [...])` note I'd left in the same docstring. My docstring had quietly become an API contract that a language model reads at inference time.

That is how tool calling works in [Hugging Face Transformers](https://github.com/huggingface/transformers), and it is worth understanding exactly, because the parts of your function you treat as documentation are the parts the model treats as instructions.

## Why this is worth a fresh look now

Transformers 5.0 shipped on January 26, 2026, the library's [first major version bump in five years](https://github.com/huggingface/transformers/releases/tag/v5.0.0). The line has moved quickly since: [version 5.15.0 landed on August 10, 2026](https://pypi.org/project/transformers/). The v5 push was largely about making the library a leaner, [PyTorch-first definition layer for the model ecosystem](https://huggingface.co/blog/transformers-v5), and one thing that carried straight through the rewrite is how the chat-template layer handles tools.

If you run open models locally instead of calling a hosted function-calling API, this path is the path. The model doesn't receive your Python function. It receives text, and the text is built from your function by a small utility called `get_json_schema`. Knowing what that utility reads (and what it refuses to accept) is the difference between a tool the model uses correctly and one it guesses at.

## What `get_json_schema` actually reads

`get_json_schema` lives in `transformers.utils`. Give it a function, and it returns an OpenAI-style tool schema built from two sources: the function's **type hints** and its **Google-style docstring**. Here is a well-documented function and the schema it produces.

```python
from transformers.utils import get_json_schema

def get_current_temperature(location: str, unit: str) -> float:
    """
    Get the current temperature at a location.

    Args:
        location: The location to get the temperature for, in the format "City, Country"
        unit: The unit to return the temperature in. (choices: ["celsius", "fahrenheit"])
    """
    return 22.0
```

Three things map across that you should notice. The `str` type hint becomes `"type": "string"`. The one-line summary at the top of the docstring becomes the tool's `description`. And the `(choices: [...])` marker inside the `unit` argument's description becomes a JSON Schema `enum`, so the model is told those are the only two legal values. That last one is easy to miss and genuinely useful: constraining an argument to an enum is a docstring annotation, not a code change.

The requirements are spelled out in the function's own source. It "requires that the function has a docstring, and that each argument has a description in the docstring, in the standard Google docstring format," and "that all user-facing arguments have valid Python type hints" ([`chat_template_utils.py`](https://github.com/huggingface/transformers/blob/main/src/transformers/utils/chat_template_utils.py)). Implicit `self` and `cls` receivers are ignored, and a `Returns:` block is optional because most chat templates drop the return value anyway.

### Defaults and Optional quietly change the contract

Two Python conventions carry real meaning into the schema. A parameter with a default value stops being required, and `typing.Optional` marks the field nullable:

```python
from typing import Optional
from transformers.utils import get_json_schema

def search(query: str, limit: int = 10, category: Optional[str] = None) -> str:
    """
    Search the catalog.

    Args:
        query: The search term.
        limit: Max number of results to return.
        category: Restrict results to one category.
    """
    return "..."
```

Running `get_json_schema(search)` reports `required: ['query']` alone. The `limit` argument, because it has a default, is optional. The `category` argument, typed `Optional[str]`, comes out as `{"type": "string", "nullable": true, ...}`. Your function signature is doing double duty as the tool's calling convention, and the model sees the result.

## The strict part: underdocumented functions are rejected

This is the behavior I most wanted to confirm by hand, because a silent failure here would be dangerous. If `get_json_schema` accepted a half-documented function and just skipped the missing pieces, the model would receive a tool description with holes in it and you would never know until it called the tool wrong.

It does not do that. It raises. I fed it three broken functions: one with an argument missing from the docstring, one with a missing type hint, and one with no docstring at all. Every one of them failed loudly, with a message naming the exact problem:

```
missing_arg_doc: DocstringParsingException: Cannot generate JSON schema for
  missing_arg_doc because the docstring has no description for the argument 'unit'
missing_type_hint: TypeHintParsingException: Argument location is missing a
  type hint in function missing_type_hint
no_docstring: DocstringParsingException: Cannot generate JSON schema for
  no_docstring because it has no docstring!
```

Two distinct exception types, both exported from `transformers.utils.chat_template_utils`: `DocstringParsingException` for documentation problems and `TypeHintParsingException` for missing hints. The practical consequence is that you cannot ship a tool the model can't understand, at least not through this path. The library forces the description to exist before it will let the function reach a model.

## Where the schema goes

The schema isn't the end of the story. It exists to be rendered into the prompt. When you call `apply_chat_template(tools=[...])`, the template layer walks your tool list and, for any entry that is a callable rather than a dict, converts it with `get_json_schema` before rendering ([`chat_template_utils.py`, lines 517–523](https://github.com/huggingface/transformers/blob/main/src/transformers/utils/chat_template_utils.py)). That is the whole chain: Python function, to JSON schema, to prompt text, to model.

I confirmed the last hop with a minimal tool-aware template so I could see the injected text directly, without downloading a model. Passing the `get_current_temperature` function straight through produced this prompt:

```
You can call these tools:
- get_current_temperature: Get the current temperature at a location.
  args: ['location', 'unit']
<|user|> What's it like in Paris?
```

The tool name, the description, and the argument names in the prompt are all values that originated in my function. A real tool-calling template (the kind that ships with models like Qwen or Llama) serializes the full schema, enums and all, but the source is identical. What the model reads about your tool is what you wrote in Python.

## Try It Yourself

Everything above runs on CPU with no model weights and no GPU. It needs only the library and Jinja2.

```bash
pip install "transformers==5.15.0" jinja2
python walkthrough.py
```

The script has four parts: a documented function's full schema, the defaults-and-`Optional` behavior, the three rejection cases, and the prompt-injection demonstration. Here is the real, unedited output (the PyTorch notice on the first line is a stderr warning from Transformers and is expected when torch is not installed):

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

The full `walkthrough.py` is in the code repository linked at the end.

## What this changes about how you write agent tools

The takeaway is a shift in where you spend care. When the tool schema is generated from your function, the docstring stops being documentation for humans and becomes part of the prompt the model reasons over. A vague argument description is a vague instruction to the model. A missing `(choices: [...])` marker is a constraint you forgot to give it. An `Optional` you added for Python's sake tells the model the field can be omitted.

That is a good deal, because it collapses two artifacts that usually drift apart, the function and its schema, into one. But it means docstring review is now part of agent review. If you would not send a sentence to your model as an instruction, don't leave it in a tool's docstring, because that is exactly where it is going.

## Key Takeaways

- In Transformers 5.x, `get_json_schema` builds a tool's JSON schema from its **type hints and Google-style docstring**; `apply_chat_template(tools=[fn])` calls it automatically for any function you pass.
- The docstring summary becomes the tool `description`, argument descriptions become parameter descriptions, and a `(choices: [...])` note becomes a JSON Schema `enum`.
- Defaults remove an argument from `required`; `Optional[...]` marks it `nullable`. Your signature is the calling convention.
- Underdocumented functions fail loudly: `DocstringParsingException` for a missing docstring or argument description, `TypeHintParsingException` for a missing type hint. Nothing ships silently broken.
- Because the schema is rendered straight into the prompt, treat tool docstrings as model-facing instructions, and review them accordingly.

**Sources:** [Transformers v5.0.0 release (Jan 26, 2026)](https://github.com/huggingface/transformers/releases/tag/v5.0.0), [transformers on PyPI (5.15.0, Aug 10, 2026)](https://pypi.org/project/transformers/), [Transformers v5 announcement](https://huggingface.co/blog/transformers-v5), [`chat_template_utils.py` source](https://github.com/huggingface/transformers/blob/main/src/transformers/utils/chat_template_utils.py).

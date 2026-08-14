"""
transformers 5.x turns a plain Python function into the tool schema a model sees.
It reads your docstring and type hints to do it -- and rejects functions that
are underdocumented. Runnable end to end with no model download and no GPU.

    pip install "transformers==5.15.0" jinja2
    python walkthrough.py
"""
import json
from typing import Optional

from transformers.utils import get_json_schema
from transformers.utils.chat_template_utils import (
    DocstringParsingException,
    TypeHintParsingException,
)
from transformers.utils.chat_template_utils import render_jinja_template


def rule(title):
    print("\n" + "=" * 4, title, "=" * 4)


# --- 1. A documented function becomes an OpenAI-style tool schema ------------
rule("1. docstring + type hints -> JSON schema")


def get_current_temperature(location: str, unit: str) -> float:
    """
    Get the current temperature at a location.

    Args:
        location: The location to get the temperature for, in the format "City, Country"
        unit: The unit to return the temperature in. (choices: ["celsius", "fahrenheit"])
    Returns:
        The current temperature at the specified location in the specified units, as a float.
    """
    return 22.0


print(json.dumps(get_json_schema(get_current_temperature), indent=2))


# --- 2. Defaults and Optional change the contract ---------------------------
rule("2. defaults drop from 'required'; Optional -> nullable")


def search(query: str, limit: int = 10, category: Optional[str] = None) -> str:
    """
    Search the catalog.

    Args:
        query: The search term.
        limit: Max number of results to return.
        category: Restrict results to one category.
    """
    return "..."


s = get_json_schema(search)["function"]["parameters"]
print("required:", s["required"])
print("limit   :", json.dumps(s["properties"]["limit"]))
print("category:", json.dumps(s["properties"]["category"]))


# --- 3. Underdocumented functions are rejected, not silently shipped ---------
rule("3. what gets rejected")


def missing_arg_doc(location: str, unit: str) -> float:
    """
    Get the current temperature.

    Args:
        location: The city.
    """
    return 22.0


def missing_type_hint(location, unit: str) -> float:
    """
    Get temp.

    Args:
        location: The city.
        unit: The unit.
    """
    return 22.0


def no_docstring(location: str) -> float:
    return 22.0


for fn in (missing_arg_doc, missing_type_hint, no_docstring):
    try:
        get_json_schema(fn)
        print(f"{fn.__name__}: (no error)")
    except (DocstringParsingException, TypeHintParsingException) as e:
        print(f"{fn.__name__}: {type(e).__name__}: {e}")


# --- 4. This is exactly what ends up in the prompt --------------------------
rule("4. the schema is injected into the prompt the model reads")

template = (
    "{% if tools %}You can call these tools:\n"
    "{% for t in tools %}- {{ t.function.name }}: {{ t.function.description }}\n"
    "  args: {{ t.function.parameters.properties.keys() | list }}\n"
    "{% endfor %}{% endif %}"
    "{% for m in messages %}<|{{ m.role }}|> {{ m.content }}\n{% endfor %}"
)

out = render_jinja_template(
    conversations=[[{"role": "user", "content": "What's it like in Paris?"}]],
    tools=[get_current_temperature],  # a plain Python function, not a dict
    chat_template=template,
)
rendered = out[0][0] if isinstance(out, tuple) else out
print(rendered)

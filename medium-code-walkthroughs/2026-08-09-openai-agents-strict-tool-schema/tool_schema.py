"""What schema does the OpenAI Agents SDK actually send the model for your tool?

Run against openai-agents 0.19.4. No API key or network call is made: building a
FunctionTool and reading `.params_json_schema` is a pure, local operation.
"""
import json
from typing import Optional

from agents import function_tool


def show(schema: dict, *keys: str) -> None:
    print("  required:", schema["required"])
    print("  additionalProperties:", schema.get("additionalProperties"))
    for k in keys:
        print(f"  {k}:", json.dumps(schema["properties"][k]))


# 1. The default: strict schema. Two required params, two with Python defaults.
@function_tool
def search_flights(
    origin: str,
    destination: str,
    max_price: float = 500.0,
    nonstop: bool = False,
) -> str:
    """Search for flights between two cities.

    Args:
        origin: IATA code of the departure airport.
        destination: IATA code of the arrival airport.
        max_price: Maximum ticket price in USD to consider.
        nonstop: If True, only return nonstop flights.
    """
    return "ok"


print("[1] strict schema (the default), strict_json_schema =",
      search_flights.strict_json_schema)
show(search_flights.params_json_schema, "max_price")

# 2. The same function, strict mode turned off.
@function_tool(strict_mode=False)
def search_flights_loose(
    origin: str,
    destination: str,
    max_price: float = 500.0,
    nonstop: bool = False,
) -> str:
    """Search for flights between two cities.

    Args:
        origin: IATA code of the departure airport.
        destination: IATA code of the arrival airport.
        max_price: Maximum ticket price in USD to consider.
        nonstop: If True, only return nonstop flights.
    """
    return "ok"


print("\n[2] strict_mode=False, strict_json_schema =",
      search_flights_loose.strict_json_schema)
show(search_flights_loose.params_json_schema, "max_price")

# 3. Making a parameter genuinely optional TO THE MODEL under strict mode:
#    a nullable type, not a Python default.
@function_tool
def search_with_optional(city: str, when: Optional[str] = None) -> str:
    """Search near a city.

    Args:
        city: The city to search in.
        when: Optional ISO timestamp; omit to search now.
    """
    return "ok"


print("\n[3] Optional[str] = None under strict mode")
show(search_with_optional.params_json_schema, "when")

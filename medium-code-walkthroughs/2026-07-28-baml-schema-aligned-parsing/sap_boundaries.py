"""Where SAP stops: it coerces shape and format, but not meaning.
An enum value with no match, or a missing required field, is a hard error."""
from baml_client import b
from baml_py import errors

cases = [
    ("enum value not in schema ('urgent')",
     '{"summary":"x","priority":"urgent","effort_days":1,"tags":["a"]}'),
    ("required field 'summary' absent",
     '{"priority":"Low","effort_days":1,"tags":["a"]}'),
]
for label, raw in cases:
    print(f"=== {label} ===")
    try:
        b.parse.TriageTicket(raw)
    except errors.BamlError as e:
        print(f"{type(e).__name__} -> {str(e).splitlines()[0]}")
    print()

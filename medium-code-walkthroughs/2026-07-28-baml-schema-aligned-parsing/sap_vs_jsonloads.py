"""What Schema-Aligned Parsing does that json.loads() can't.
Runs entirely offline: b.parse.* only invokes the parser, never the model."""
import json
from baml_client import b

raw = '''I looked at the report. This is clearly urgent, here you go:

```json
{
  "summary": "Checkout page returns 500 on payment submit",
  "priority": "high",
  "effort_days": "2 days",
  "tags": "billing",
}
```'''

print("=== json.loads() ===")
try:
    json.loads(raw)
except json.JSONDecodeError as e:
    print(f"JSONDecodeError -> {e}")

print("\n=== b.parse.TriageTicket() ===")
t = b.parse.TriageTicket(raw)
print("returned:", type(t).__name__)
print("priority   ->", repr(t.priority), "  (", type(t.priority).__name__, ")")
print("effort_days->", repr(t.effort_days), "        (", type(t.effort_days).__name__, ")")
print("tags       ->", repr(t.tags), "     (", type(t.tags).__name__, ")")
print("summary    ->", t.summary)

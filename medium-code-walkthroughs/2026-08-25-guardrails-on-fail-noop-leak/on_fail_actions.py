"""Guardrails AI 0.11.0 — what each on_fail action returns for the SAME failing value.
No LLM or API key: guard.validate() runs the validator on a fixed string."""
from guardrails import Guard, OnFailAction
from guardrails.validator_base import Validator, register_validator, PassResult, FailResult


@register_validator(name="no-api-key", data_type="string")
class NoApiKey(Validator):
    """Fails any text that looks like it leaked an API key."""
    def validate(self, value, metadata):
        if "sk-" in value:
            return FailResult(error_message="Output contains an API-key-like token.",
                              fix_value="[REDACTED]")
        return PassResult()


BAD = "sure, your key is sk-abc123"

# None == "let the validator use its default action"
actions = [None, OnFailAction.NOOP, OnFailAction.FIX,
           OnFailAction.FILTER, OnFailAction.REFRAIN, OnFailAction.EXCEPTION]

print(f"input: {BAD!r}\n")
print(f"{'on_fail':<22}{'passed':<8}{'validated_output'}")
print("-" * 60)
for action in actions:
    validator = NoApiKey() if action is None else NoApiKey(on_fail=action)
    label = "(default)" if action is None else str(action).split(".")[-1].lower()
    guard = Guard().use(validator)
    try:
        outcome = guard.validate(BAD)
        print(f"{label:<22}{str(outcome.validation_passed):<8}{outcome.validated_output!r}")
    except Exception as exc:
        print(f"{label:<22}{'—':<8}RAISES {type(exc).__name__}")

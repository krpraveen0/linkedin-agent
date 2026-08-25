"""The realistic mistake: on_fail="noop", then use validated_output as if it were safe.
Guardrails 0.11.0. No LLM needed."""
from guardrails import Guard
from guardrails.validator_base import Validator, register_validator, PassResult, FailResult


@register_validator(name="no-api-key", data_type="string")
class NoApiKey(Validator):
    def validate(self, value, metadata):
        if "sk-" in value:
            return FailResult(error_message="Output contains an API-key-like token.")
        return PassResult()


model_output = "sure, your key is sk-abc123"

# "noop" sounds harmless: just note the problem, don't blow up.
guard = Guard().use(NoApiKey(on_fail="noop"))
outcome = guard.validate(model_output)

# The natural thing to write, and the bug.
print("shipping to user:", outcome.validated_output)

# The verdict lived in a different field the whole time.
print("validation_passed:", outcome.validation_passed)
for s in outcome.validation_summaries:
    print("summary:", s.failure_reason)

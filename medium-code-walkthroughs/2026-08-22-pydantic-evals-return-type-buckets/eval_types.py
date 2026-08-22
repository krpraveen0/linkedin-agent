"""Two evaluators with identical intent. One returns a bool, one returns an int.
pydantic-evals sorts them into different report sections purely by return type.
No LLM or API key: the 'task' under test is a plain Python function.
"""
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext


# The "system under test": a trivial keyword sentiment guesser. No model, no network.
def classify(text: str) -> str:
    return "positive" if "love" in text.lower() else "negative"


class MatchesBool(Evaluator[str, str, str]):
    """Return a Python bool: 'did the output equal the expected label?'"""
    def evaluate(self, ctx: EvaluatorContext[str, str, str]) -> bool:
        return ctx.output == ctx.expected_output


class MatchesInt(Evaluator[str, str, str]):
    """Same check, but return 1 for pass and 0 for fail instead of True/False."""
    def evaluate(self, ctx: EvaluatorContext[str, str, str]) -> int:
        return 1 if ctx.output == ctx.expected_output else 0


dataset = Dataset[str, str, str](
    name="sentiment-check",
    cases=[
        Case(name="clear_positive", inputs="I love this",   expected_output="positive"),
        Case(name="wrong_guess",    inputs="This is fine",  expected_output="positive"),
    ],
    evaluators=[MatchesBool(), MatchesInt()],
)

if __name__ == "__main__":
    report = dataset.evaluate_sync(classify)
    report.print(include_input=True, include_output=True, include_expected_output=True)

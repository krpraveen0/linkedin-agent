"""Prove the bucketing is purely type-driven, even though Python says True == 1."""
from eval_types import dataset, classify

report = dataset.evaluate_sync(classify, progress=False)
case = report.cases[0]  # the "clear_positive" case: both evaluators pass

print("Python thinks 1 == True:", 1 == True)
print("assertions bucket:", list(case.assertions))
print("scores bucket:    ", list(case.scores))

b = case.assertions["MatchesBool"].value
i = case.scores["MatchesInt"].value
print(f"MatchesBool -> {b!r} ({type(b).__name__}) counted toward pass rate")
print(f"MatchesInt  -> {i!r} ({type(i).__name__}) counted as a score, not a pass/fail")

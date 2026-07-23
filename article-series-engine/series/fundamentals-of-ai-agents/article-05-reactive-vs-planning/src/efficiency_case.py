"""
Case 1: a task where the whole sequence can be correctly determined
WITHOUT observing any intermediate results - fetch the weather for
three cities and compute the average. Planning wins here, and the
efficiency difference is real and countable, not just asserted.
"""

WEATHER_DATA = {"NYC": 68, "LA": 75, "Chicago": 61}


def fetch_weather(city: str) -> int:
    return WEATHER_DATA[city]


def run_reactive(cities: list[str]) -> tuple[list[str], int]:
    """Reactive: one decision-maker call per step - decide, act,
    observe, decide again. This is Articles 01-02's loop, applied here."""
    decision_calls = 0
    actions = []
    temps = []
    for city in cities:
        decision_calls += 1  # "decide next action" - a real call every time
        actions.append(f"fetch({city})")
        temps.append(fetch_weather(city))
    decision_calls += 1  # one more decision: what to do once fetching is done
    actions.append("compute_average")
    return actions, decision_calls


def run_planning(cities: list[str]) -> tuple[list[str], int]:
    """Planning: ONE decision-maker call produces the whole plan up
    front. Execution then just follows the plan - no more calls to the
    decision-maker needed, because nothing here depends on what any
    individual fetch actually returns."""
    decision_calls = 1  # the entire plan, decided once
    plan = [f"fetch({city})" for city in cities] + ["compute_average"]
    return plan, decision_calls


if __name__ == "__main__":
    cities = ["NYC", "LA", "Chicago"]

    actions, calls = run_reactive(cities)
    print(f"Reactive: {actions}")
    print(f"  decision-maker calls: {calls}\n")

    actions, calls = run_planning(cities)
    print(f"Planning: {actions}")
    print(f"  decision-maker calls: {calls}")

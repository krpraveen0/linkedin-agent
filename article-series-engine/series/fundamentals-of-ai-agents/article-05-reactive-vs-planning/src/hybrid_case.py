"""
Case 3: a hybrid. Fetch weather for three cities (nothing about any
one fetch depends on another - plan this part), then decide whether
to send a rain alert (this genuinely depends on what got fetched -
stay reactive for this one step).
"""

import sys
sys.path.insert(0, ".")
from efficiency_case import fetch_weather

RAIN_DATA = {"NYC": False, "LA": False, "Chicago": True}


def run_hybrid(cities: list[str]) -> tuple[list[str], int]:
    decision_calls = 1  # ONE call plans the fetches - they don't depend on each other
    actions = [f"fetch({city})" for city in cities]

    rain_observed = any(RAIN_DATA[city] for city in cities)  # the actual observation

    decision_calls += 1  # ONE more call - but only because this step's
    # correct action genuinely depends on what was just observed
    if rain_observed:
        actions.append("send_rain_alert")
    else:
        actions.append("no_alert_needed")

    return actions, decision_calls


if __name__ == "__main__":
    cities = ["NYC", "LA", "Chicago"]
    actions, calls = run_hybrid(cities)
    print(f"Hybrid: {actions}")
    print(f"  decision-maker calls: {calls}")
    print("  (2 calls: one plans the independent fetches, one reacts to")
    print("   what they actually found - not 4 calls like pure reactive,")
    print("   not a fixed guess like pure planning would have to make)")

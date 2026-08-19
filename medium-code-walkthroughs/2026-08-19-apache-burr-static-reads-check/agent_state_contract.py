"""
Burr parses the SOURCE of your action to check you declared every state key
you read -- and it does it the moment @action wraps the function, before you
build or run anything. Verified against apache-burr 0.42.0.

Run: python agent_state_contract.py
"""
from burr.core import action, State, ApplicationBuilder, expr


# --- 1. A tiny "agent turn" loop that declares its reads/writes honestly ---
@action(reads=["turn", "limit"], writes=["turn"])
def take_turn(state: State) -> State:
    return state.update(turn=state["turn"] + 1)


@action(reads=["turn"], writes=[])
def report(state: State) -> State:
    return state


def build_loop():
    return (
        ApplicationBuilder()
        .with_actions(take_turn=take_turn, report=report)
        .with_transitions(
            ("take_turn", "take_turn", expr("turn < limit")),
            ("take_turn", "report", expr("turn >= limit")),
        )
        .with_state(turn=0, limit=3)
        .with_entrypoint("take_turn")
        .build()
    )


# --- plain functions; we attach @action by hand so we can catch the result ---
def take_turn_buggy(state: State) -> State:
    ceiling = state["limit"]                 # literal subscript, never declared
    return state.update(turn=state["turn"] + 1)


def via_get(state: State) -> State:
    ceiling = state.get("limit")             # not a literal subscript
    return state.update(turn=state["turn"] + 1)


def no_annotation(state):                    # param not typed as State
    ceiling = state["limit"]
    return state.update(turn=state["turn"] + 1)


if __name__ == "__main__":
    print("== 1. honest loop ==")
    _, _, s = build_loop().run(halt_after=["report"])
    print("final turn:", s["turn"], "/ limit:", s["limit"])

    print("\n== 2. forgot to declare a read ==")
    try:
        action(reads=["turn"], writes=["turn"])(take_turn_buggy)
    except ValueError as e:
        print("ValueError:", e)

    print("\n== 3a. state.get() is invisible to the check ==")
    action(reads=["turn"], writes=["turn"])(via_get)
    print("wrapped: no error (state.get is not a literal subscript)")

    print("\n== 3b. no ': State' annotation skips the check ==")
    action(reads=["turn"], writes=["turn"])(no_annotation)
    print("wrapped: no error (Burr never found the state parameter)")

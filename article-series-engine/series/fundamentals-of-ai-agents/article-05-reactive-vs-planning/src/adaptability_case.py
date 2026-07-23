"""
Case 2: a task where the correct NEXT step genuinely depends on what
gets observed - check a server's status, and only restart it if it's
actually down. Planning fails here in a real, demonstrable way: the
plan has to be fixed before observing the real status.
"""


def check_status(server_status: str) -> str:
    return server_status  # standing in for a real health-check call


def run_reactive(server_status: str) -> list[str]:
    """Reactive: observes the actual status, THEN decides whether to
    restart. The decision is made after the observation exists."""
    actions = ["check_status"]
    observed = check_status(server_status)
    if observed == "down":
        actions.append("restart")
    else:
        actions.append("no_action_needed")
    return actions


def run_planning_forced_upfront() -> list[str]:
    """Planning: the WHOLE plan has to be committed before anything is
    observed - that is ReWOO's real, documented limitation (Xu et al.,
    2023): plans cannot adapt mid-execution to a result that wasn't
    known when the plan was made. Forced to guess, this plan commits to
    always restarting - which is wrong whenever the server is actually
    fine."""
    plan = ["check_status", "restart"]  # committed BEFORE the real status is known
    return plan


if __name__ == "__main__":
    print("Server is actually DOWN:")
    print(f"  reactive plan:  {run_reactive('down')}  (correct - restarts because it observed 'down')")
    print(f"  fixed plan:     {run_planning_forced_upfront()}  (also happens to restart - fine here)\n")

    print("Server is actually UP (the interesting case):")
    print(f"  reactive plan:  {run_reactive('up')}  (correct - observed 'up', does nothing)")
    print(f"  fixed plan:     {run_planning_forced_upfront()}  (WRONG - restarts a server that was never down,")
    print("                   because the plan was committed before the real status was ever known)")

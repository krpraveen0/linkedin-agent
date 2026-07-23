"""
Step 4: the actual testable definition.

A system is agentic, by this test, if its action sequence genuinely
changes shape between two meaningfully different environments - not
just different data plugged into the same fixed steps, but a
different SET of steps because the system actually decided based on
what it observed.

A workflow and a "loop that calls a model a fixed number of times"
both fail this test, even though one of them technically uses an LLM.
"""

import sys
sys.path.insert(0, ".")
from step1_workflow import run_workflow
from step2_fake_loop import run_fake_loop
from step3_real_agent import run_agent


def is_agentic(system, empty_env, real_task_env) -> tuple[bool, str]:
    """Runs the same system on an environment with nothing to do and
    an environment with a real task, and checks whether the action
    sequence actually differs."""
    actions_empty = system(empty_env)
    actions_real = system(real_task_env)

    if actions_empty == actions_real:
        return False, (
            f"identical action sequence in both environments "
            f"({actions_empty}) - the system isn't reading the "
            f"environment to decide what to do, it's just running "
            f"the same steps regardless"
        )
    return True, (
        f"different action sequences: {actions_empty} vs {actions_real} "
        f"- next steps genuinely depended on what was observed"
    )


if __name__ == "__main__":
    empty_inbox = []
    real_inbox = ["urgent: server down"]

    print("Testing the workflow from Step 1:")
    result, reason = is_agentic(run_workflow, empty_inbox, real_inbox)
    print(f"  agentic: {result} - {reason}\n")

    print("Testing the fake loop from Step 2:")
    result, reason = is_agentic(run_fake_loop, empty_inbox, real_inbox)
    print(f"  agentic: {result} - {reason}\n")

    print("Testing the real agent from Step 3:")
    result, reason = is_agentic(run_agent, empty_inbox, real_inbox)
    print(f"  agentic: {result} - {reason}")

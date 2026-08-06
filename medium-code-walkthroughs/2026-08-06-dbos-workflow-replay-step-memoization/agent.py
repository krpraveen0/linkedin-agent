import os
from dbos import DBOS, DBOSConfig

# Zero-config: no database_url given, so DBOS uses a local SQLite file.
DBOS(config=DBOSConfig(name="research-agent"))

EFFECTS = "effects.log"
FINISH_FLAG = "allow_finish.flag"

def record(line: str) -> None:
    # A side channel OUTSIDE the DBOS database. If a line appears twice,
    # that code really executed twice.
    with open(EFFECTS, "a") as f:
        f.write(f"{line} (pid={os.getpid()})\n")

@DBOS.step()
def plan(topic: str) -> str:
    record("STEP  plan")
    return f"outline for '{topic}'"

@DBOS.step()
def gather(outline: str) -> int:
    record("STEP  gather")
    return len(outline)  # pretend this was an expensive tool call

@DBOS.step()
def write(outline: str, facts: int) -> str:
    record("STEP  write")
    return f"draft({facts} facts) from {outline}"

@DBOS.workflow()
def research_agent(topic: str) -> str:
    record("BODY  start")
    outline = plan(topic)
    facts = gather(outline)
    record("BODY  after gather")           # <- plain body code, NOT a step
    if not os.path.exists(FINISH_FLAG):
        record("BODY  crashing before write")
        os._exit(1)                         # hard crash: no cleanup, like SIGKILL
    draft = write(outline, facts)
    record("BODY  done")
    return draft

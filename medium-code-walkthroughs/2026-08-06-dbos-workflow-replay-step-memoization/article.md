# I Crashed My AI Agent Between Two Steps. DBOS Reran the Workflow From the Top — but Not the Steps It Had Already Finished.

An agent that calls three tools and dies after the second one is a real problem, not a hypothetical. The model spent tokens on step one, your code spent a paid API call on step two, and then the pod got evicted. Restart naively and you pay for both again. Durable execution is the fix, and in the last few weeks it got cheap enough to try in a scratch file: [DBOS Transact for Python](https://pypi.org/project/dbos/) shipped `2.29.0` on July 30, 2026, and it now runs on a local SQLite file with no configuration at all.

So I ran the experiment. I built a three-step "research agent," killed the process hard between step two and step three, and restarted it. The recovery behavior was more specific than "it resumes" — and the specific part is the part that will bite you if you don't know it. DBOS reran my workflow function *from the first line*, but the two steps that had already finished never executed again. Here is exactly what ran twice, what ran once, and why that distinction decides where you're allowed to put a side effect.

## Why this is worth caring about now

Agents are long-running processes that make external calls, and long-running processes crash. The standard answer is durable execution: checkpoint progress to a database so a restart resumes instead of restarting. That idea isn't new, but two things made it timely enough to write real code against.

First, DBOS dropped its infrastructure requirement. The library runs fully in-process and, with no `database_url` supplied, [defaults to a local SQLite system database](https://docs.dbos.dev/python/programming-guide) — no Postgres server, no Docker, no config file. I confirmed this empirically below; the first launch just creates a `.sqlite` file and applies its schema.

Second, agent frameworks are wiring durable execution in as a first-class feature. Pydantic AI added a durable-execution layer with a [dedicated DBOS integration](https://ai.pydantic.dev/durable_execution/dbos/), and shipped fixes to it as recently as [`v2.14.1` on July 21, 2026](https://github.com/pydantic/pydantic-ai/releases). When your agent framework is about to run your tool calls as durable steps, it's worth understanding what "durable step" actually means before you rely on it.

## The claim, stated precisely

DBOS's fault-tolerance model rests on two operations: it [checkpoints workflows and steps](https://docs.dbos.dev/architecture) to the system database, and on failure it recovers from the last completed step. The DBOS documentation is blunt about the guarantee — once a step completes and is checkpointed, it is never re-executed — and about the mechanism: on recovery, DBOS restarts each interrupted workflow *by calling it again with its checkpointed inputs*.

Read those two facts together and a subtlety falls out. "Restart the workflow by calling it again" means your `@DBOS.workflow` function runs from the top. "A completed step is never re-executed" means each `@DBOS.step` call inside it short-circuits to the value it returned last time. So on recovery, the code *between* your steps runs again, and the code *inside* your finished steps does not. Everyone quotes the first half. The second half is where the bugs live.

## Try It Yourself

Everything below runs on a laptop with `pip install dbos` (I used `dbos==2.29.0`, Python 3.11) and nothing else — no database server, no API keys.

Here's the agent. Each step and each line of the workflow body appends to a plain text file *outside* the DBOS database, so we can see exactly what executed. The workflow crashes itself with `os._exit(1)` — a hard kill with no cleanup — the first time through, guarded by a flag file so the recovered run can get past it.

```python
# agent.py
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
```

The runner starts the workflow under a fixed ID on the first pass and reattaches to it on the second. `DBOS.launch()` is where recovery happens: on startup DBOS finds any workflow a previous process left pending and resumes it.

```python
# run.py
import sys
from dbos import DBOS, SetWorkflowID
from agent import research_agent

WID = "research-agent-001"
mode = sys.argv[1]  # "start" or "resume"

DBOS.launch()  # on launch, DBOS recovers any workflow left pending by a crash

if mode == "start":
    with SetWorkflowID(WID):
        handle = DBOS.start_workflow(research_agent, "durable agents")
    print("RESULT:", handle.get_result())   # process is killed mid-way on run 1
elif mode == "resume":
    handle = DBOS.retrieve_workflow(WID)     # attach to the recovered workflow
    print("RESULT:", handle.get_result())
```

Now run it: start it (it crashes), drop the finish flag, and resume it.

```
$ python run.py start
INFO  No workflows to recover from application version 493afac9...
INFO  DBOS launched!
$ cat effects.log
BODY  start (pid=6950)
STEP  plan (pid=6950)
STEP  gather (pid=6950)
BODY  after gather (pid=6950)
BODY  crashing before write (pid=6950)

$ touch allow_finish.flag
$ python run.py resume
INFO  Recovering 1 workflows from application version 493afac9...
INFO  DBOS launched!
RESULT: draft(28 facts) from outline for 'durable agents'
```

The full `effects.log` after both runs is the whole story:

```
BODY  start (pid=6950)              <- run 1
STEP  plan (pid=6950)
STEP  gather (pid=6950)
BODY  after gather (pid=6950)
BODY  crashing before write (pid=6950)
BODY  start (pid=6962)              <- run 2 (recovered, new PID)
BODY  after gather (pid=6962)
STEP  write (pid=6962)
BODY  done (pid=6962)
```

Look at what the recovered process (`pid=6962`) did. `BODY start` and `BODY after gather` appear a second time: the workflow function genuinely re-executed from line one. But `STEP plan` and `STEP gather` do **not** appear a second time. Those steps had completed and been checkpointed in run 1, so on recovery their recorded outputs were returned without calling the functions again. Only `STEP write`, the one step that never finished, ran in the new process. And the final answer — `28 facts` — is correct, carried across a process boundary from a step that ran in a PID that no longer exists.

That "28" isn't reconstructed; it's read back from disk. The system database keeps a row per completed step:

```python
# inspect_db.py
import sqlite3
db = sqlite3.connect("research_agent.sqlite")   # app name -> file name
db.row_factory = sqlite3.Row

print("workflow_status:")
for r in db.execute("SELECT workflow_uuid, status, name, recovery_attempts "
                    "FROM workflow_status"):
    print(f"  id={r['workflow_uuid']}  status={r['status']}  "
          f"recovery_attempts={r['recovery_attempts']}")

print("\noperation_outputs (the memoized step checkpoints):")
for r in db.execute("SELECT function_id, function_name, output "
                    "FROM operation_outputs ORDER BY function_id"):
    print(f"  step#{r['function_id']}  {r['function_name']:<8}  output={r['output']}")
```

```
workflow_status:
  id=research-agent-001  status=SUCCESS  recovery_attempts=2

operation_outputs (the memoized step checkpoints):
  step#1  plan      output=gASVIAAAAAAAAACMHG91dGxpbmUgZm9yICdkdXJhYmxlIGFnZW50cyeULg==
  step#2  gather    output=gARLHC4=
  step#3  write     output=gASVNQAAAAAAAACMMWRyYWZ0KDI4IGZhY3RzKSBmcm9tIG91dGxpbmUgZm9yICdkdXJhYmxlIGFnZW50cyeULg==
```

The workflow finished `SUCCESS` after `recovery_attempts=2`, and each step's return value is sitting in `operation_outputs` as a base64-wrapped pickle. Decode step two's blob — `gARLHC4=` — and you get the integer `28`: the exact value `gather` returned before the crash, which is why the recovered `write` step could run without `gather` ever executing again.

## The gotcha: your workflow body is not a step

Here's the practical consequence, and it's the reason to run this yourself before shipping. Any code in the workflow function that isn't wrapped in a step will run again on every recovery. In my demo that was harmless `record()` calls. In a real agent it might be a `requests.post`, a database `INSERT`, a Slack message, or a counter increment — and each of those would fire a second time after a crash-and-resume, because the workflow body re-executes while the finished steps don't.

The rule the mechanism forces on you: put anything with a side effect *inside* a step. Steps are the unit of exactly-once execution; the workflow body is the unit of deterministic replay. Non-deterministic or externally-visible work in the body breaks the assumption — DBOS's recovery is correct precisely because it expects the body to be a deterministic skeleton that stitches checkpointed step results together. This is also why the docs describe workflows as needing to be deterministic: the body is going to run again, and it had better do the same thing when it does.

## Key Takeaways

- **DBOS recovery is not "resume where you left off" line-by-line.** It re-invokes the workflow function from the top with the original inputs, and completed `@DBOS.step` calls return their checkpointed results instead of re-running.
- **Code between steps runs on every recovery.** The workflow body is replayed; only finished steps are memoized. Put every side effect inside a step, or it will happen again after a crash.
- **You can try durable execution with zero infrastructure.** `dbos==2.29.0` defaults to a local SQLite system database when no `database_url` is set — first launch creates the file and migrates it.
- **The checkpoints are inspectable.** Step outputs live in the `operation_outputs` table and workflow state in `workflow_status`; you can read exactly what was memoized with plain `sqlite3`.
- **This is landing in agent frameworks.** Pydantic AI's DBOS integration (fixes as recent as July 21, 2026) means these semantics will govern your tool calls whether or not you call DBOS directly — so know which of your code is a "step."

*This walkthrough was produced by an automated daily pipeline; the code and its output were executed and captured directly, but a human accuracy pass is still recommended before treating any of it as production guidance.*

**Sources:** [DBOS Transact on PyPI (v2.29.0, July 30, 2026)](https://pypi.org/project/dbos/) · [DBOS Architecture — checkpointing workflows and steps](https://docs.dbos.dev/architecture) · [DBOS Workflow Recovery](https://docs.dbos.dev/production/workflow-recovery) · [DBOS Python Programming Guide](https://docs.dbos.dev/python/programming-guide) · [Pydantic AI — DBOS durable execution](https://ai.pydantic.dev/durable_execution/dbos/) · [Pydantic AI releases (v2.14.1, July 21, 2026)](https://github.com/pydantic/pydantic-ai/releases)

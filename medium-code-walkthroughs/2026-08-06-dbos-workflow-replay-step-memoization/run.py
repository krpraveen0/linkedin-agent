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

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

"""How the allowlist works - and how widening it removes the protection.

`additional_authorized_imports` is opt-in. Adding a module lets the agent
import it. Adding the wildcard "*" turns the import check off entirely, at
which point "restricted" Python becomes ordinary Python.

Runs fully offline. The only shell command executed is a harmless `id`.
"""

from smolagents.local_python_executor import (
    evaluate_python_code,
    BASE_BUILTIN_MODULES,
    BASE_PYTHON_TOOLS,
)


def run(label, code, authorized):
    try:
        out, _ = evaluate_python_code(
            code, static_tools=BASE_PYTHON_TOOLS, authorized_imports=authorized
        )
        print(f"{label}: OK -> {out!r}")
    except Exception as e:
        msg = str(e).split(" due to: ")[-1].strip()
        print(f"{label}: BLOCKED -> {msg}")


# Narrow allowlist: one extra module, nothing more.
run("import math  [+math]", "import math\nmath.sqrt(16)", BASE_BUILTIN_MODULES + ["math"])

# The convenience wildcard some tutorials reach for.
run("import os    [+'*']", "import os\nos.getcwd()", ["*"])
run("os.system id [+'*']", "import os\nos.system('id')", ["*"])

"""What smolagents' LocalPythonExecutor blocks by default.

Runs fully offline against smolagents' AST interpreter. No API key, no model.
"""

import smolagents
from smolagents.local_python_executor import (
    evaluate_python_code,
    BASE_BUILTIN_MODULES,
    BASE_PYTHON_TOOLS,
    DANGEROUS_MODULES,
    DANGEROUS_FUNCTIONS,
)

print("smolagents", smolagents.__version__)
print("default authorized modules:", BASE_BUILTIN_MODULES)
print("blocked modules   :", DANGEROUS_MODULES)
print("blocked functions :", DANGEROUS_FUNCTIONS)
print()


def run(label, code):
    try:
        out, _ = evaluate_python_code(
            code,
            static_tools=BASE_PYTHON_TOOLS,
            authorized_imports=BASE_BUILTIN_MODULES,
        )
        print(f"{label}: OK -> {out!r}")
    except Exception as e:
        # Report only the interpreter's own message, not the Python traceback.
        msg = str(e).split(" due to: ")[-1].strip()
        print(f"{label}: BLOCKED -> {msg}")


run("plain math      ", "sum(i * i for i in range(5))")
run("import os       ", "import os\nos.getcwd()")
run("dunder attribute", "().__class__")
run("builtins eval   ", "eval('1 + 1')")
run("runaway loop    ", "i = 0\nwhile True:\n    i += 1")

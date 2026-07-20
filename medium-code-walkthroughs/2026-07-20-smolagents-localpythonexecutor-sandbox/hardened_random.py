"""The `random._os` gotcha, re-checked against the installed version.

smolagents' own security docs warn that the default-authorized `random`
module exposes `random._os`. This checks whether that path is still open in
the version actually installed.
"""

import smolagents
from smolagents.local_python_executor import (
    evaluate_python_code,
    BASE_BUILTIN_MODULES,
    BASE_PYTHON_TOOLS,
)

print("smolagents", smolagents.__version__)
try:
    out, _ = evaluate_python_code(
        "import random\nrandom._os.getcwd()",
        static_tools=BASE_PYTHON_TOOLS,
        authorized_imports=BASE_BUILTIN_MODULES,  # default allowlist only
    )
    print("random._os reachable -> os.getcwd() =>", repr(out))
except Exception as e:
    msg = str(e).split(" due to: ")[-1].strip()
    print("random._os BLOCKED ->", msg)

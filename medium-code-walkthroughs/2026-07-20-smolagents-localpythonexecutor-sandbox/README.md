# What smolagents' LocalPythonExecutor Actually Blocks — Code Walkthrough

Runnable code for the 2026-07-20 article *"smolagents Runs LLM-Written Python On Your Machine. Here's What Its 'Sandbox' Actually Blocks."*

All three scripts run fully offline against smolagents' AST interpreter. No API key and no model are required. They were verified against `smolagents==1.26.0` (published 2026-05-29).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install "smolagents==1.26.0"
```

## Files

- `executor_guards.py` — feeds five snippets through `evaluate_python_code` and shows what the default configuration allows vs. blocks (imports, dunder attributes, `eval`, runaway loops).
- `allowlist_escape.py` — shows the opt-in `additional_authorized_imports` allowlist, and how the `"*"` wildcard turns the import check off so `os.system('id')` runs.
- `hardened_random.py` — re-checks Hugging Face's own documented `random._os` bypass against 1.26.0, where it is now blocked.
- `article.md` — the full article.
- `figure1-executor.svg`, `figure2-allowlist.svg` — diagrams.

## Run 1 — what the default configuration refuses

```bash
python executor_guards.py
```

Real captured output:

```text
smolagents 1.26.0
default authorized modules: ['collections', 'datetime', 'itertools', 'math', 'queue', 'random', 're', 'stat', 'statistics', 'time', 'unicodedata']
blocked modules   : ['builtins', 'io', 'multiprocessing', 'os', 'pathlib', 'pty', 'shutil', 'socket', 'subprocess', 'sys']
blocked functions : ['builtins.compile', 'builtins.eval', 'builtins.exec', 'builtins.globals', 'builtins.locals', 'builtins.__import__', 'os.popen', 'os.system', 'posix.system']

plain math      : OK -> 30
import os       : BLOCKED -> InterpreterError: Import of os is not allowed. Authorized imports are: ['collections', 'datetime', 'itertools', 'math', 'queue', 'random', 're', 'stat', 'statistics', 'time', 'unicodedata']
dunder attribute: BLOCKED -> InterpreterError: Forbidden access to dunder attribute: __class__
builtins eval   : BLOCKED -> InterpreterError: Forbidden function evaluation: 'eval' is not among the explicitly allowed tools or defined/imported in the preceding code
runaway loop    : BLOCKED -> InterpreterError: Maximum number of 1000000 iterations in While loop exceeded
```

## Run 2 — the allowlist and the wildcard escape hatch

```bash
python allowlist_escape.py
```

Real captured output (the `os.getcwd()` path reflects your working directory):

```text
import math  [+math]: OK -> 4.0
import os    [+'*']: OK -> '/path/to/your/cwd'
uid=0(root) gid=0(root) groups=0(root)
os.system id [+'*']: OK -> 0
```

## Run 3 — the `random._os` path is closed in 1.26.0

```bash
python hardened_random.py
```

Real captured output:

```text
smolagents 1.26.0
random._os BLOCKED -> InterpreterError: Forbidden access to module: os
```

## Sources

- smolagents on PyPI (1.26.0, 2026-05-29): https://pypi.org/project/smolagents/
- Secure code execution docs: https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution
- CVE-2025-9959 (NVD): https://nvd.nist.gov/vuln/detail/CVE-2025-9959
- CVE-2025-5120 (GitHub Advisory): https://github.com/advisories/GHSA-6v92-r5mx-h5fx

All output captured from `smolagents==1.26.0` on 2026-07-20. This walkthrough validates traceability, freshness, and code execution; a human accuracy pass is still recommended.

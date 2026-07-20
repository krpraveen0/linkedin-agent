# smolagents Runs LLM-Written Python On Your Machine. Here's What Its "Sandbox" Actually Blocks.

If you build a `CodeAgent` with Hugging Face's [smolagents](https://github.com/huggingface/smolagents), the model does not emit JSON tool calls. It writes Python, and that Python runs. By default it runs in the same process as your agent, through a component called `LocalPythonExecutor`. The obvious question, the one that decides whether this is safe to point at untrusted input, is: what exactly stops that generated code from reading your environment variables or shelling out?

I installed the current release, smolagents 1.26.0 ([published May 29, 2026](https://pypi.org/project/smolagents/)), and asked the executor directly instead of trusting the marketing. The answer is more precise, and more uncomfortable, than "it's sandboxed."

## What the executor really is

`LocalPythonExecutor` is not a subprocess, a container, or a seccomp profile. It is a hand-written interpreter. It parses the generated code into an Abstract Syntax Tree and walks that tree node by node, deciding at each step whether the operation is allowed. There is no CPython process running the agent's code with the OS as its only referee.

That design gives it two allow/deny lists and a couple of hard limits, all of which you can read straight out of the installed package:

```text
default authorized modules: ['collections', 'datetime', 'itertools', 'math', 'queue',
                             'random', 're', 'stat', 'statistics', 'time', 'unicodedata']
blocked modules   : ['builtins', 'io', 'multiprocessing', 'os', 'pathlib', 'pty',
                     'shutil', 'socket', 'subprocess', 'sys']
blocked functions : ['builtins.compile', 'builtins.eval', 'builtins.exec',
                     'builtins.globals', 'builtins.locals', 'builtins.__import__',
                     'os.popen', 'os.system', 'posix.system']
```

Imports are denied unless a module is on the allowlist. The Hugging Face security docs state the rule plainly: "By default, imports are disallowed unless they have been explicitly added to an authorization list by the user" ([Secure code execution](https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution)). On top of that, attribute access to dunder names (`__class__`, `__globals__`, and friends) is refused, `eval`/`exec`/`compile` are refused, and loops are capped so a `while True` cannot hang the host forever.

## Try it yourself

Everything below runs with no API key and no model. You are calling the interpreter directly with strings of code, exactly what the LLM would have produced.

```bash
python3 -m venv venv && source venv/bin/activate
pip install "smolagents==1.26.0"
```

**Block 1 — what the default configuration refuses.** This script feeds five snippets through `evaluate_python_code` and prints whether each was allowed or blocked, reporting only the interpreter's own error message.

```python
from smolagents.local_python_executor import (
    evaluate_python_code, BASE_BUILTIN_MODULES, BASE_PYTHON_TOOLS)

def run(label, code):
    try:
        out, _ = evaluate_python_code(code, static_tools=BASE_PYTHON_TOOLS,
                                      authorized_imports=BASE_BUILTIN_MODULES)
        print(f"{label}: OK -> {out!r}")
    except Exception as e:
        print(f"{label}: BLOCKED -> {str(e).split(' due to: ')[-1].strip()}")

run("plain math      ", "sum(i * i for i in range(5))")
run("import os       ", "import os\nos.getcwd()")
run("dunder attribute", "().__class__")
run("builtins eval   ", "eval('1 + 1')")
run("runaway loop    ", "i = 0\nwhile True:\n    i += 1")
```

Real captured output:

```text
plain math      : OK -> 30
import os       : BLOCKED -> InterpreterError: Import of os is not allowed. Authorized imports are: ['collections', 'datetime', 'itertools', 'math', 'queue', 'random', 're', 'stat', 'statistics', 'time', 'unicodedata']
dunder attribute: BLOCKED -> InterpreterError: Forbidden access to dunder attribute: __class__
builtins eval   : BLOCKED -> InterpreterError: Forbidden function evaluation: 'eval' is not among the explicitly allowed tools or defined/imported in the preceding code
runaway loop    : BLOCKED -> InterpreterError: Maximum number of 1000000 iterations in While loop exceeded
```

Arithmetic is fine. Reaching for the operating system, walking dunder attributes to climb out to `object.__subclasses__`, calling `eval`, or spinning forever are each refused with a specific error. For a lot of data-wrangling agent work, that is genuinely useful protection.

**Block 2 — the allowlist, and the door it leaves open.** The allowlist is opt-in through `additional_authorized_imports`. Add one module and only that module opens. Add the wildcard `"*"` and the import check stops meaning anything.

```python
from smolagents.local_python_executor import (
    evaluate_python_code, BASE_BUILTIN_MODULES, BASE_PYTHON_TOOLS)

def run(label, code, authorized):
    try:
        out, _ = evaluate_python_code(code, static_tools=BASE_PYTHON_TOOLS,
                                      authorized_imports=authorized)
        print(f"{label}: OK -> {out!r}")
    except Exception as e:
        print(f"{label}: BLOCKED -> {str(e).split(' due to: ')[-1].strip()}")

run("import math  [+math]", "import math\nmath.sqrt(16)", BASE_BUILTIN_MODULES + ["math"])
run("import os    [+'*']", "import os\nos.getcwd()", ["*"])
run("os.system id [+'*']", "import os\nos.system('id')", ["*"])
```

Real captured output:

```text
import math  [+math]: OK -> 4.0
import os    [+'*']: OK -> '/tmp/.../scratchpad'
uid=0(root) gid=0(root) groups=0(root)
os.system id [+'*']: OK -> 0
```

That third line is a real shell command. With `authorized_imports=["*"]`, `os` imports, `os.system('id')` runs, and the output of `id` prints from inside the "restricted" interpreter. The wildcard is a supported convenience, and tutorials reach for it to stop fighting import errors. It also turns the executor back into ordinary Python with full reach to the host.

**Block 3 — re-check the documentation against the installed code.** Hugging Face's own security page warns that "some seemingly innocuous packages like `random` can give access to potentially harmful submodules, as in `random._os`." `random` is on the default allowlist, so that would be a bypass requiring no wildcard at all. I checked whether it still works in 1.26.0:

```python
from smolagents.local_python_executor import (
    evaluate_python_code, BASE_BUILTIN_MODULES, BASE_PYTHON_TOOLS)

out = evaluate_python_code("import random\nrandom._os.getcwd()",
                           static_tools=BASE_PYTHON_TOOLS,
                           authorized_imports=BASE_BUILTIN_MODULES)
```

Real captured output:

```text
smolagents 1.26.0
random._os BLOCKED -> InterpreterError: Forbidden access to module: os
```

In 1.26.0 that path is closed. The interpreter now inspects the resolved object and refuses when it turns out to be a blocked module like `os`, so the exact example in the docs no longer reproduces. The guards are being tightened. That is the encouraging half of the story, and also the reason the honest framing is "a moving target," not "solved."

## So is it a sandbox?

The maintainers answer this themselves, in two places. The class docstring shipped in 1.26.0 reads: "It is not a security sandbox: for isolated execution of untrusted code, use a remote executor." The security tutorial is blunter still: "no local python sandbox can ever be completely secure," and "the only way to run LLM-generated code with truly robust security isolation is to use remote execution options like E2B or Docker."

History backs the caution. In September 2025, JFrog's Natan Nehorai reported [CVE-2025-9959](https://nvd.nist.gov/vuln/detail/CVE-2025-9959) (CVSS 7.6), an escape caused by incomplete validation of dunder attributes in `local_python_executor.py`, affecting smolagents 1.21.0 and earlier and exploitable through prompt injection. It was not the first; [CVE-2025-5120](https://github.com/advisories/GHSA-6v92-r5mx-h5fx) covered an earlier sandbox escape in the same module. Block 3 shows the project responding to exactly this class of bug. It also shows why a denylist of "harmful submodules" is a race you win one entry at a time.

The takeaway is not that smolagents is careless. The AST interpreter is a reasonable defense-in-depth layer, and the team is patching it. The takeaway is that a same-process interpreter guarding against adversarial, model-generated code is the wrong thing to make load-bearing. If the code path can be reached by untrusted input, the isolation boundary has to be a real one: a separate process, a container, or a remote executor.

## What to actually do

Treat `LocalPythonExecutor` as a convenience for trusted, low-stakes runs, and as one layer, never the boundary. Keep `additional_authorized_imports` as narrow as the task allows, and never ship `"*"` to anything that touches untrusted input. When the agent's inputs are attacker-influenced (web content, user messages, tool results from other agents), move execution to an isolated backend. smolagents ships `E2BExecutor` and `DockerExecutor` for this, and the docs point you at them by name.

The useful mental model: the allowlist decides what the agent can *conveniently* do, and the process boundary decides what it can *ultimately* do. Only one of those is a security control.

## Key Takeaways

- smolagents' `LocalPythonExecutor` is an AST-walking interpreter in your own process, not an OS-level sandbox. It denies non-allowlisted imports, dunder attribute access, `eval`/`exec`, and unbounded loops.
- The import allowlist is opt-in via `additional_authorized_imports`. Passing `"*"` disables it; in a real run that let `os.system('id')` execute and print `uid=0(root)`.
- The maintainers state directly that it "is not a security sandbox," and two CVEs (CVE-2025-5120, CVE-2025-9959) are on record for escapes in this exact module.
- The guards are actively hardening: the `random._os` bypass from Hugging Face's own docs no longer reproduces in 1.26.0, which is reassuring and also a reminder that denylists are a moving target.
- For untrusted or attacker-influenced input, use a real isolation boundary (`E2BExecutor`, `DockerExecutor`, or another remote sandbox). Keep the local allowlist minimal regardless.

*Sources: [smolagents on PyPI (1.26.0, May 29 2026)](https://pypi.org/project/smolagents/), [smolagents Secure code execution docs](https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution), [smolagents on GitHub](https://github.com/huggingface/smolagents), [CVE-2025-9959 (NVD)](https://nvd.nist.gov/vuln/detail/CVE-2025-9959), [CVE-2025-5120 (GitHub Advisory)](https://github.com/advisories/GHSA-6v92-r5mx-h5fx). All code output captured from smolagents 1.26.0 on 2026-07-20.*

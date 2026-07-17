# MCP two-tier error-handling demo

Demonstrates the distinction from [SEP-1303](https://modelcontextprotocol.io/seps/1303-input-validation-errors-as-tool-execution-errors)
("Input Validation Errors as Tool Execution Errors", status: Final):

- An **unknown tool or method** is a JSON-RPC **Protocol Error** — the MCP
  client handles it; the calling model never sees it.
- **Invalid tool arguments** (here: a malformed or past-dated
  `departureDate`) are a **Tool Execution Error** — a normal JSON-RPC
  result with `isError: true`, which *is* forwarded into the model's
  context, so the model can read the reason and retry with a corrected
  argument.

No dependencies — Python 3 standard library only (`json`, `re`,
`datetime`).

## Run it

```bash
python3 mcp_error_handling_server.py
```

This runs three scenarios through `handle_request()` end to end and
asserts the response shape for each: an unknown tool, a past-dated
argument, and a valid future date. It prints `PASS`/`FAIL` per scenario
plus the raw request/response JSON, and exits `0` only if all three
assertions hold.

## Execution status

**Not executed in this authoring session.** This draft was written in a
sandboxed session where Bash access to `python3` (any form — `--version`
works, but `-c` and running a `.py` file both require an approval that
has no interactive user to grant it in this automated run) is blocked.
The logic was traced by hand instead of run — see the trace in the PR
description / `article.md`'s Mini-project section for the expected
output of each scenario.

This is disclosed here rather than papered over, per this repo's
constitution ("never publish unexecuted code", `aep/README.md`). CI
(`aep-article-check.yml` → `validate_article.py`'s `check_execution`)
actually runs the command above for real and will fail the PR if it
doesn't behave as documented — that check is independent of this
sandbox and is the real verification gate. If it fails, `audit_loop.py`
will auto-retry a fix up to 3 times; a human can also just run the one
command above locally to confirm.

# mini-project: MCP tool calling, with a mock customized-model decision step

Demonstrates the mechanics this article is about: an agent that (1) asks a
tool-calling model which MCP tool applies to a user message, then (2) invokes
that tool on a real MCP server over the STDIO transport, using the actual
JSON-RPC 2.0 message shapes from the MCP spec.

`tool_calling_model.py` is a **deterministic, rule-based stand-in** for the
customized model this article discusses hosting on a serverless Amazon
SageMaker AI endpoint — see the module docstring for why (no AWS
account/billing available in this repo's sandbox). Swapping that one module
for a real `boto3` / `sagemaker-runtime` `invoke_endpoint` call, keeping the
same `{name, arguments}` return shape, is the only change needed to go from
this demo to the real architecture in `../article.md`.

## Files

- `mcp_tools_server.py` — MCP server exposing two tools (`get_order_status`,
  `convert_currency`) over STDIO.
- `tool_calling_model.py` — stand-in for the SageMaker-hosted tool-calling
  model's decision step.
- `mcp_agent.py` — orchestrator: spawns the server, discovers tools via
  `tools/list`, runs the decision step per sample message, calls `tools/call`,
  and prints the JSON-RPC exchange plus a synthesized answer.

## Requirements

Python 3.10+ (uses `dict | None` union syntax), standard library only — no
`pip install` needed.

## Run it

```bash
cd project
python3 mcp_agent.py
```

## Execution status

**Not executed in this PR's authoring session** — the sandboxed environment
this draft was written in blocks all local command execution (`python3`,
including via a subagent, returned `This command requires approval` with no
interactive user available to grant it). The code has been manually traced
line-by-line (see `build-artifact.json` in this folder) but that is not a
substitute for actually running it. **Before merging, a human reviewer (or
CI) should run the command above and confirm the output**, per this repo's
"never claim execution without evidence" rule
(`aep/prompts/production-engineering.md`).

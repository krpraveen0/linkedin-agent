# Agent dispatch: Copilot, Claude Code, opencode

How the deterministic pipeline (`aep/pipelines/run_pipeline.py`) hands off to an
actual coding agent for the generative steps (research expansion, writing,
audits) — and why three different agents get three different trigger
mechanisms, not one uniform one.

## Why not identical for all three

All three read the exact same contracts — `aep/prompts/*.md` (role/output
requirements) and `aep/schemas/*.json` (output shape) — so switching which
agent does the writing is just a matter of which one you invoke. But only one
of them currently has a working *unattended, scheduled, free-cloud* path:

| Agent | Unattended/scheduled? | Why |
|---|---|---|
| **Copilot coding agent** | ✅ Yes | GitHub-native async cloud agent, billed against your Copilot subscription seat (not a metered API key) — complies with `aep/policies/no-external-llm-policy.md`, which explicitly allows "GitHub-native Copilot agent capabilities." |
| **Claude Code** | ⚠️ Manual only | `anthropics/claude-code-action` has an [open bug](https://github.com/anthropics/claude-code-action/issues/814) where `schedule:`-triggered runs fail auth (OIDC/permissions), even though manual and comment triggers work fine. Revisit once that's fixed. |
| **opencode** | ❌ Local only | No hosted free-cloud agent product exists for opencode — it's a CLI you run yourself, and its non-interactive CI mode has [documented gaps](https://github.com/anomalyco/opencode/issues/13851) for "send a prompt, apply changes" automation. |

## 1. Copilot coding agent — scheduled, automatic

`aep-morning-research.yml` runs `run_pipeline.py`, then — if configured —
`aep/pipelines/dispatch_to_copilot.py` opens a GitHub issue for the
top-ranked topic and assigns it to `copilot-swe-agent[bot]` via the Issues
API. Copilot then works asynchronously on GitHub's own infrastructure and
opens a draft PR. No LLM API key is ever stored in this repo — the dispatch
script only talks to the GitHub REST API.

**Setup (one-time):**
1. Requires a Copilot plan with coding-agent access (Pro, Pro+, Business,
   Enterprise — GitHub Student Developer Pack includes Pro).
2. Create a **fine-grained PAT** ([github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens))
   scoped to this repo with: `Issues: Read & write`, `Pull requests: Read &
   write`, `Contents: Read & write`, `Metadata: Read`.
3. Add it as repo secret `COPILOT_DISPATCH_PAT`
   (Settings → Secrets and variables → Actions).
4. That's it — the next scheduled or manual `aep-morning-research` run will
   dispatch automatically. Without the secret set, that step no-ops and only
   the deterministic artifacts are generated (current default behavior).

**Manual test without spending a real dispatch:**
```bash
python3 aep/pipelines/run_pipeline.py --mode morning
python3 aep/pipelines/dispatch_to_copilot.py --mode morning --dry-run
```

## 2. Claude Code — manual trigger

`aep-claude-manual.yml` runs Claude Code via the official
`anthropics/claude-code-action@v1`, authenticated with
`claude_code_oauth_token` (Claude Pro/Max subscription auth — no metered
`ANTHROPIC_API_KEY`, no per-token billing). Deliberately **not** on a
`schedule:` trigger (see table above) — trigger it yourself:

- **Button**: Actions tab → "aep-claude-manual" → Run workflow → pick
  `mode: morning` or `evening`.
- **Comment**: mention `@claude` in any issue or PR comment (e.g. on the
  issue Copilot opened, to ask Claude for a second pass).

**Setup (one-time):**
1. Locally, with your Claude Pro/Max login: `claude setup-token` — this
   mints an OAuth token tied to your subscription, not a pay-per-call key.
2. Add it as repo secret `CLAUDE_CODE_OAUTH_TOKEN`.

## 3. opencode — local, on demand

No workflow file — run it yourself against the latest artifacts:

```bash
python3 aep/pipelines/run_pipeline.py --mode morning   # refresh artifacts locally
opencode run "Follow aep/prompts/research.md then aep/prompts/writer.md to draft \
an article from the latest run under aep/out/morning/ (see last-run.json). \
Emit output matching aep/schemas/publish-draft.schema.json, status \
'Draft - Pending Human Approval'."
```

Point opencode at whatever backend you've configured it with (your GitHub
Copilot or Claude subscription, or a fully local model) — that choice is
yours, not something this repo hardcodes.

## Constitution note

`aep/policies/no-external-llm-policy.md` bans `aep/pipelines/*.py` from
embedding LLM API calls (hardcoded, silently-billed integration). Invoking
an actual agent product as an explicit, visible, human-authorized step (a
workflow file you can read, or a command you type yourself) is categorically
different and is how the generative phases were always meant to work per the
roadmap in `aep/docs/implementation-spec.md` ("Phase 3+: writer/diagram
agents"). `dispatch_to_copilot.py` only ever calls the GitHub REST API.

# Agent dispatch: Copilot, Claude Code, opencode

How the deterministic pipeline (`aep/pipelines/run_pipeline.py`) hands off to an
actual coding agent for the generative steps (research expansion, writing,
audits) — and why three different agents get three different trigger
mechanisms, not one uniform one.

## What "publish-ready" actually requires

Every article — regardless of which agent writes it — must land as a complete
folder under `articles/**` (a series `part-NN/`, or a standalone slug):
hero image, content with an embedded topic-specific diagram and real code
snippets, and a runnable `project/` mini-project. The full spec is
`aep/prompts/writer.md`; it's not optional or prose-only. Two mechanical
enforcements exist so this isn't just a prompt suggestion:

- `python3 aep/pipelines/validate_article.py <article-dir>` — run this
  yourself before opening a PR (the dispatch issue and the Claude Code prompt
  both tell the agent to do this).
- `.github/workflows/aep-article-check.yml` — runs the same check
  automatically on any PR touching `articles/**`, whoever opened it.

## Why not identical for all three

All three read the exact same contracts — `aep/prompts/*.md` (role/output
requirements) and `aep/schemas/*.json` (output shape) — so switching which
agent does the writing is just a matter of which one you invoke. But only one
of them currently has a working *unattended, scheduled, free-cloud* path:

| Agent | Unattended/scheduled? | Why |
|---|---|---|
| **Copilot coding agent** | ✅ Yes (primary) | GitHub-native async cloud agent, billed against your Copilot subscription seat (not a metered API key) — complies with `aep/policies/no-external-llm-policy.md`, which explicitly allows "GitHub-native Copilot agent capabilities." If assignment fails (e.g. quota exhausted), the dispatch script automatically falls back to posting an `@claude` comment — see section 1 below. |
| **Claude Code** | ⚠️ Manual only | `anthropics/claude-code-action` has an [open bug](https://github.com/anthropics/claude-code-action/issues/814) where `schedule:`-triggered runs fail auth (OIDC/permissions), even though manual and comment triggers work fine. Revisit once that's fixed. |
| **opencode** | ❌ Local only | No hosted free-cloud agent product exists for opencode — it's a CLI you run yourself, and its non-interactive CI mode has [documented gaps](https://github.com/anomalyco/opencode/issues/13851) for "send a prompt, apply changes" automation. |

## 1. Copilot coding agent — scheduled, automatic, with a Claude fallback

`aep-morning-research.yml` runs `run_pipeline.py`, then — if configured —
`aep/pipelines/dispatch_to_agent.py`:
1. Creates a GitHub issue for the top-ranked topic (target folder, prompt
   contracts, full deliverables checklist).
2. Tries to assign it to `copilot-swe-agent[bot]` via the Issues API.
3. **If that assignment call fails — including Copilot premium-request quota
   exhaustion — it posts an `@claude` comment on the same issue instead.**
   That's a genuine `issue_comment` event, which `aep-claude-manual.yml`
   picks up reliably (unlike a `schedule:` trigger, which is why the
   fallback goes through a comment rather than invoking Claude Code directly
   inside this same cron job — see the cron-bug note in the table above).

Copilot then works asynchronously on GitHub's own infrastructure (or Claude
Code does, if it took over) and opens a draft PR. No LLM API key is ever
stored in this repo — the dispatch script only talks to the GitHub REST API.

**Known limitation**: this only catches a failure *at assignment time*. If
Copilot's agent session starts successfully but then fails or stalls
mid-task (e.g. quota runs out partway through), that's asynchronous and
outside this script's visibility — you'd need to notice the issue sitting
unresolved and manually trigger the Claude fallback (`@claude` comment, or
the `aep-claude-manual.yml` workflow_dispatch button) yourself.

**Setup (one-time):**
1. Requires a Copilot plan with coding-agent access (Pro, Pro+, Business,
   Enterprise — GitHub Student Developer Pack includes Pro) for the primary
   path, and `CLAUDE_CODE_OAUTH_TOKEN` (see section 2 below) for the
   fallback to actually work.
2. Create a **fine-grained PAT** ([github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens))
   scoped to this repo with: `Issues: Read & write`, `Pull requests: Read &
   write`, `Contents: Read & write`, `Metadata: Read`. This same PAT covers
   both the Copilot assignment call and the fallback comment — no separate
   secret needed for the fallback itself.
3. Add it as repo secret `COPILOT_DISPATCH_PAT`
   (Settings → Secrets and variables → Actions).
4. That's it — the next scheduled or manual `aep-morning-research` run will
   dispatch automatically. Without the secret set, that step no-ops and only
   the deterministic artifacts are generated (current default behavior).

**Manual test without spending a real dispatch:**
```bash
python3 aep/pipelines/run_pipeline.py --mode morning
python3 aep/pipelines/dispatch_to_agent.py --mode morning --dry-run
# Preview the fallback path too, without needing real quota exhaustion:
python3 aep/pipelines/dispatch_to_agent.py --mode morning --dry-run --simulate-copilot-failure
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
agents"). `dispatch_to_agent.py` only ever calls the GitHub REST API.

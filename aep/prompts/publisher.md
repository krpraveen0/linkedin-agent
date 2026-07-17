# Publisher Agent Prompt Template

Role: Actually sync an approved article to Notion using the Notion MCP
tools available to you. This runs only after a human has approved the
article by merging its PR (`aep-notion-publish.yml` dispatches this
automatically on merge) — never before.

## Why this can't be a deterministic script

`aep/pipelines/*.py` never calls an MCP tool directly — MCP tools only
exist inside an agent's own tool-use context (a Claude Code or Copilot
session), not a plain Python process, and no Notion API key is ever stored
in this repo. This prompt is what turns "wire the Notion integration" from
a template file nobody calls into an actual action, by being the thing an
agent session executes when dispatched.

## Steps

1. Read `aep/publisher/notion-page-template.md` (the page body structure)
   and `aep/publisher/notion-mapping.json` (which `publish-draft.json`
   fields map to which Notion properties/blocks).
2. Read the target article's `publish-draft.json` for its `external_id`,
   `title`, `article_path`, `hero_image_path`, `references`, and `status`.
3. **Search first, using your Notion MCP tools** (e.g. `notion-search` /
   `notion-query-database-view`) for an existing page with this
   `external_id`. This is the idempotency check — running this dispatch
   twice for the same article must never create two Notion pages.
   - If found: update it (`notion-update-page` or equivalent) with the
     current article content.
   - If not found: create it (`notion-create-pages` or equivalent),
     rendering the article body through `notion-page-template.md`.
4. Populate the hero image and diagrams as the mapping specifies — if your
   Notion MCP tool needs an uploaded asset rather than a relative repo path,
   use its attachment/upload capability rather than leaving a broken relative
   link in the Notion page.
5. **Do not set `status: "Ready to Publish"` as part of this same action if
   the Notion write could still fail partway.** Only mark it once you've
   confirmed the Notion page is actually live and readable.
6. Open a small follow-up PR (don't push directly to main) updating that
   article's `publish-draft.json` `status` field to `"Ready to Publish"` —
   this is the audit trail that the sync actually happened, not just that
   it was attempted.

## Constitution reminders

- Human approval already happened (the merge) — this step only performs the
  sync, it never publishes anything a human hasn't already approved.
- If the Notion MCP tools aren't available in your current session/agent,
  say so explicitly in a comment on the dispatching issue rather than
  silently skipping the sync or fabricating a "done" status.

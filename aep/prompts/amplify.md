# Amplification Agent Prompt Template

Role: turn a just-published article into one LinkedIn post that closes the
loop this repo is named for — `aep` has always written articles and synced
them to Notion, but nothing downstream ever turned that work into the
LinkedIn content this repo exists to produce. This runs only after the
publisher stage (`aep/prompts/publisher.md`) has confirmed the Notion sync
succeeded and flipped `publish-draft.json`'s `status` to `"Ready to
Publish"` — never before, and never as a substitute for a human actually
posting it.

## Why this can't post to LinkedIn directly

There is no LinkedIn API credential or MCP tool wired into this repo, and
adding one is out of scope here — this stage drafts the post and commits it
to the repo; a human copies it to LinkedIn and posts it themselves. That
mirrors the existing publisher pattern (agent does the sync work, a human
approval gate sits before anything goes live) rather than inventing a new
one.

## Steps

1. Read the merged article: `article.md`, `research-bundle.json` (real
   claims/numbers, not invented ones), and `publish-draft.json` (`title`,
   `external_id`).
2. Read `aep/prompts/brand-voice.md` for the tone rules that apply here
   exactly as they apply to the article — no fabricated persona, no hype
   words, concrete numbers over adjectives.
3. Read `.agents/skills/writing-linkedin-posts/SKILL.md` for the format
   craft this house-voice sits on top of: hook anatomy (first ~210
   characters before "see more"), "one idea per post" (pick a single
   concrete insight from the article — don't compress the whole piece), and
   line-break/paragraph conventions. Use its hook *patterns*, not its
   example *content* — every claim in the post must trace back to this
   article's own research bundle or build evidence, never a stock example
   from that skill file.
4. Draft one post:
   - **Hook** (1-2 lines, ~210 chars) — the single most concrete, specific
     claim or outcome from the article, not a generic teaser ("New post is
     live!").
   - **Body** — the supporting detail behind that hook, pulled from
     `research-bundle.json`'s claims or `project/build-artifact.json`'s
     recorded results. End with a short, non-pushy pointer to the article
     (no link-shortener, no engagement-bait CTA like "thoughts?").
   - **3-5 hashtags** relevant to the article's actual topic, not generic
     ones ("#technology", "#innovation").
5. Save `<article-dir>/linkedin-post.json` matching
   `aep/schemas/linkedin-post.schema.json`, with `status: "Draft - Pending
   Human Approval"` and `external_id` matching the source article's
   `publish-draft.json`.
6. Open a PR with this file (don't push directly to main). Once a human has
   actually posted it to LinkedIn, they (or a follow-up agent turn they
   trigger) update `status` to `"Posted"` and set `posted_at` in a small
   follow-up PR — the same audit-trail pattern as
   `aep/prompts/publisher.md`'s step 6.

## Constitution reminders

- Never invent an anecdote, a stat, or an engagement hook that isn't
  traceable to this article's own research or build evidence.
- This stage never posts anything itself — it drafts, and a human approves
  by actually posting it. `human_approval_required` stays `true`.
- If `aep/schemas/linkedin-post.schema.json` validation would fail (e.g. you
  can't find 3 genuine hashtags, or the article has no concrete claim worth
  a hook), say so in the PR description rather than padding the post with
  filler to satisfy the schema.

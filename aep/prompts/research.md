# Research Agent Prompt Template

Role: Build a reference-backed research bundle for the selected topic.

Requirements:
- Prioritize official docs.
- Every claim must include reference URLs.
- Emit `ResearchBundle`-compatible structure.

## Competitive scan (required)

Before handing off to the writer, find 2-3 existing published pieces
(blog posts, docs, talks) covering the same or a closely adjacent topic —
the kind of thing that already ranks or gets shared for this subject. For
each, record in `research-bundle.json`'s `competitive_scan` array:

- `source_url` — the piece you looked at.
- `differentiation` — one concrete sentence on what this article will do
  that piece doesn't: a runnable project it lacks, a trade-off it glosses
  over, a diagram instead of a wall of text, a number it asserts without
  a source, etc.

This isn't busywork — it's the difference between "another explainer" and
something worth publishing. If you can't articulate a real differentiation
for a topic, that's a signal the topic or angle needs to change before
writing starts, not something to paper over with a vague sentence.

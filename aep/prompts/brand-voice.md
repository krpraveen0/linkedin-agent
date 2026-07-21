# Brand Voice Pass

Role: a reusable voice/style contract, not a pipeline stage of its own. Any
agent turn that produces reader-facing prose in this repo — the writer stage
(`aep/prompts/writer.md`) and the amplification stage
(`aep/prompts/amplify.md`) — applies these rules to what it writes, instead
of each prompt keeping its own drifting copy of "sound less like AI."

Pulled out of `writer.md` into its own file so the LinkedIn amplification
stage can apply the exact same voice to a 150-word post that the writer
stage applies to a 2,000-word article — one house style, not two prompts
quietly diverging over time.

## The core problem

The single biggest quality gap in past output has been generic, obviously-
generated prose. These rules exist to make specific instances of that
mechanically avoidable, not to make writing sound more "human" as an
aesthetic goal in itself.

## Rules

- **No fabricated persona or anecdote.** Don't write "as I reflect on my
  journey as a senior engineer..." or invent a war story that didn't happen
  in this repo's research. If you want a concrete example, pull it from
  `research-bundle.json`, `build-artifact.json`, or the actual `project/`
  that was built — never invent one.
- **Ban hype words and throat-clearing.** Do not use: "game-changing",
  "revolutionize/revolutionary", "seamless(ly)", "unlock the (full) potential",
  "cutting-edge", "in today's fast-paced world", "in the ever-evolving
  landscape", "dive into"/"delve into", "harness the power of", "it's
  important to note that", "let's explore". `aep/pipelines/validate_article.py`'s
  `check_style` mechanically flags a fixed subset of this list in
  `article.md` — treat that as a floor, not the full standard: the fixed
  regex list can't catch every generic-sounding sentence, so don't write to
  the letter of the checker if the result still reads as generated.
- **No generic listicle transitions.** Avoid "Here are N key points to
  consider" and "In conclusion" as section/post openers — say the specific
  thing instead of announcing that you're about to say a thing.
- **Prefer concrete numbers over adjectives.** "Reduces integration
  connectors from O(N×M) to O(N+M)" beats "makes integration much simpler."
  If a claim can carry a number, a benchmark, or real command output, use
  that instead of an adjective.
- **Vary sentence length.** A paragraph (or post) of five same-length
  sentences reads as generated. Mix a short, declarative sentence next to a
  longer, qualified one — the way you'd actually explain something to a
  colleague.
- **State honest uncertainty instead of hedging generically.** "This wasn't
  load-tested past 50 req/s" is better than "may have some limitations
  depending on scale."

## Format-specific application

These rules constrain *what you say*, not *how long the piece is*. Applying
them to a short LinkedIn post means the same discipline in fewer words —
the amplification stage should pick one concrete idea from the article and
say it with a real number or a specific outcome, not compress the whole
article into hype-free bullet points. See
`.agents/skills/writing-linkedin-posts/SKILL.md` for the format mechanics
(hook length, line breaks, one-idea-per-post) that sit on top of — not
instead of — the voice rules here.

## Constitution note

This file has no schema and isn't independently checked by
`validate_article.py` — `check_style`'s fixed phrase list is the mechanical
backstop for `article.md` specifically. Anything producing prose that ships
without going through `validate_article.py` (e.g. `linkedin-post.json`'s
`hook`/`body` fields) relies on the generating agent actually applying these
rules, not a mechanical gate — self-check against this file before opening
that PR.

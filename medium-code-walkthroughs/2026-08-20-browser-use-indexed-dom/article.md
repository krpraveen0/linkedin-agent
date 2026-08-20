# I Gave My browser-use Agent a Button-Shaped Div. It Never Saw a Button to Click.

I built a checkout page with a big, bordered, clickable-looking box that said "Apply discount." Then I pointed a [browser-use](https://github.com/browser-use/browser-use) agent at it and asked what it could interact with. The box was not on the list. The agent could read the words "Apply discount" as flat text, but it had no way to click them. As far as the model was concerned, there was no button there at all.

That is not a bug. It is the single most important thing to understand about how browser agents work in 2026, and browser-use makes it unusually easy to see. The library never hands the model your raw HTML. It walks the live DOM, throws away almost everything, and sends the model a short list of numbered elements it has decided are worth acting on. If your element does not make that list, the agent is blind to it.

I ran this against `browser-use==0.13.8`, released on [PyPI](https://pypi.org/project/browser-use/) on August 16, 2026, and read its source to confirm exactly why the box disappeared.

## Why the agent sees a list, not a page

A raw HTML page is a terrible prompt. It is thousands of tokens of nested `<div>`s, inline styles, tracking scripts, and SVG paths, most of which a model can neither click nor learn from. Browser-use solves this by building what it calls a serialized DOM state: a compact, indexed text view where every line is an element the agent is allowed to act on, tagged with a numeric index like `[19]`. When the model wants to click, it does not produce a CSS selector or coordinates. It says "click element 19," and browser-use maps that index back to a real DOM node.

This is the layer that changed most recently. Browser-use spent its early life driving Chrome through Playwright, then [switched to talking to Chrome directly over the Chrome DevTools Protocol](https://browser-use.com/changelog/19-8-2025) (CDP). You can confirm the migration is complete without reading a single blog post — just look at what the installed package depends on:

```
$ pip show browser-use | tr ',' '\n' | grep -iE 'cdp|playwright'
 cdp-use
```

There is no Playwright in the dependency tree anymore. `cdp-use` is there instead. That matters for this article because CDP is what lets browser-use pull the accessibility tree, computed cursor styles, and paint order straight from the browser — the exact signals it uses to decide which elements are real controls and which are just decoration.

## The two-gate rule that hid my box

The decision about what goes in the list is not clever AI. It is a plain boolean, and you can read it in the installed source. In `browser_use/dom/serializer/serializer.py`, the collector that gathers indexable elements guards on this:

```python
if is_interactive and is_visible:
```

Both gates have to pass. My "Apply discount" box failed the first one, and the hidden admin button on the same page failed the second.

`is_interactive` is decided by a heuristic in [`clickable_elements.py`](https://raw.githubusercontent.com/browser-use/browser-use/main/browser_use/dom/serializer/clickable_elements.py). An element is considered interactive if it is a natural control (a `<button>`, `<a>`, `<input>`), if it carries an interactive ARIA or accessibility-tree role, if it has one of a specific set of event-handler attributes, or if its computed cursor is a pointer. The event-handler set is explicit in the code:

```python
interactive_attributes = {'onclick', 'onmousedown', 'onmouseup', 'onkeydown', 'onkeyup', 'tabindex'}
```

Read that list against my two `<div>`s. The one I called `realdiv` had an `onclick` attribute, so it matched and got an index. The one I called `fakebtn` had only a `style` attribute — a border, some padding, a gray background — and no handler, no role, no `tabindex`, and no `cursor: pointer`. It matched nothing. To browser-use it was a styled container that happened to hold text, indistinguishable from a paragraph.

The important nuance: browser-use does not detect whether a real JavaScript click listener is attached. It pattern-matches on tags, roles, attributes, and cursor style. A `<div>` that looks and behaves like a button to a human, but was wired up with `addEventListener` in a separate script and never given a role or a pointer cursor, can fall straight through this net. That is a genuine failure mode for agents on modern component-framework sites, where clickable things are frequently plain `<div>`s.

The second gate, `is_visible`, is why my hidden button vanished. It was a real `<button>` — it would have passed the interactivity check easily — but it carried `display: none`. An invisible interactive element is dropped from the list entirely, which is the behavior you want: an agent should not be able to trigger a control a user cannot see.

## Try It Yourself

You do not need an API key or an LLM to watch this happen. The serialization step runs entirely in the browser layer, so you can print the exact text a model would receive.

First, a page with one of each case — a real button, a real link, a real input, a styled box with no handler, a `<div>` with an `onclick`, and a hidden button:

```html
<button id="pay">Pay now</button>
<a id="terms" href="/terms">Read the terms</a>
<input id="coupon" type="text" placeholder="Coupon code">

<!-- Looks like a button, but no handler, no role, no pointer cursor -->
<div id="fakebtn" style="border:1px solid #333;padding:6px;display:inline-block;background:#eee">Apply discount</div>

<!-- A div that is actually wired up -->
<div id="realdiv" onclick="void 0" style="border:1px solid #333;padding:6px;display:inline-block">Gift wrap</div>

<!-- Interactive, but hidden -->
<button id="hidden" style="display:none">Secret admin action</button>
```

Then load it and print `dom_state.llm_representation()` — the same method browser-use calls when it builds the prompt:

```python
import asyncio
from browser_use.browser import BrowserProfile, BrowserSession

async def main():
    session = BrowserSession(browser_profile=BrowserProfile(
        executable_path="/path/to/chrome", headless=True, args=["--no-sandbox"]))
    await session.start()
    try:
        await session.navigate_to("http://localhost:8099/page.html")
        await session.get_browser_state_summary()          # warm the snapshot
        state = await session.get_browser_state_summary()
        print(state.dom_state.llm_representation())
        print("indexed:", len(state.dom_state.selector_map))
    finally:
        await session.kill()

asyncio.run(main())
```

Here is the real, unedited output:

```
===== WHAT THE LLM SEES (dom_state.llm_representation) =====
Checkout
[19]<button id=pay />
	Pay now
[24]<a id=terms />
	Read the terms
|SHADOW(open)|[2]<input id=coupon type=text placeholder=Coupon code />
Apply discount
[4]<div id=realdiv />
	Gift wrap
===== INTERACTIVE ELEMENTS THE AGENT CAN ACT ON =====
[19] <button id=pay>
[24] <a id=terms>
[2] <input id=coupon>
[4] <div id=realdiv>
total: 4
```

Four elements got indices. Read the middle of that block carefully: `Apply discount` appears as a bare line of text with no `[N]` in front of it. The agent can read it but cannot target it. The `Secret admin action` button does not appear at all. And notice the indices are `19`, `24`, `2`, `4` — not `1, 2, 3, 4`. They are assigned per snapshot and are not tied to reading order, so never assume they count up the page. (The `|SHADOW(open)|` marker on the input is browser-use surfacing the shadow DOM that Chrome builds inside every text field — also real, also unedited.)

The indices are less stable than they look. The *set* of indexed elements is reliable: the four controls are always indexed, "Apply discount" is always bare text, the hidden button is always absent, and the total is always four. But the exact number changes between runs — across seven fresh runs the input came back as `[2]` six times and `[3]` once, and `get_browser_state_summary()` returns the same wobble even on a warmed second read. That instability is the strongest possible argument for the rule below: treat an index as valid for one snapshot only, and never hard-code it.

## What this means for your automation

If you are building on any indexed-DOM browser agent — browser-use, or the several frameworks that copied this design — the practical rules follow directly from the two gates:

- If your agent "can't find" a control, check the element before you touch the prompt. If it is a `<div>` or `<span>` with a click listener but no `role`, no `tabindex`, and no pointer cursor, the model never received it. The fix is on the page, not in the instructions: add `role="button"` and `tabindex="0"`, or a `cursor: pointer` style.
- Anything behind `display: none`, a zero-size box, or an off-screen position is intentionally invisible to the agent. A control that only appears after a hover or a menu-open is not in the list until that state exists.
- Do not hard-code element indices across steps. They are snapshot-scoped and derived from browser-internal IDs.

The serialized DOM is the actual interface between your page and the model. When an agent misbehaves, the first thing to inspect is not the reasoning trace — it is this list, because it defines the entire universe of things the agent was ever able to do.

## Key Takeaways

- Browser-use (v0.13.8, released 2026-08-16) sends the LLM an indexed text list of elements, never raw HTML. Each actionable element gets a `[N]` index the model uses to act.
- An element is included only if `is_interactive and is_visible` — both gates, verified in the installed `serializer.py`.
- Interactivity is a heuristic over tags, ARIA/accessibility roles, a fixed set of event-handler attributes (`onclick`, `tabindex`, and four others), and a pointer cursor. It does not detect real JS listeners, so a styled `<div>` with no role can be invisible to the agent.
- Hidden-but-real controls (`display: none`) are dropped by the visibility gate.
- Indices are not tied to page order and are scoped to a single snapshot — the same input came back as `[2]` or `[3]` across fresh runs, so never hard-code them.
- browser-use 0.13.x drives Chrome over CDP with no Playwright dependency — confirmed directly in the installed package.

## Sources

- browser-use source (`clickable_elements.py`, interactivity heuristic), GitHub: https://raw.githubusercontent.com/browser-use/browser-use/main/browser_use/dom/serializer/clickable_elements.py — and the `is_interactive and is_visible` gate verified against the installed `browser-use==0.13.8` source (`browser_use/dom/serializer/serializer.py`), inspected 2026-08-20
- browser-use on PyPI (version 0.13.8, released 2026-08-16; 0.13.0 released 2026-06-08): https://pypi.org/project/browser-use/
- browser-use changelog, "We switched from Playwright to CDP" (2025): https://browser-use.com/changelog/19-8-2025 — the migration is corroborated empirically here: the installed 0.13.8 depends on `cdp-use`, with no Playwright in its dependency tree
- browser-use repository: https://github.com/browser-use/browser-use
- Runnable code and real captured output (auto-generated by the daily-medium-article cloud routine): the `medium-code-walkthroughs/2026-08-20-browser-use-indexed-dom/` folder in this repository

# What a browser-use agent actually "sees"

Runnable code for the article **"I Gave My browser-use Agent a Button-Shaped Div. It Never Saw a Button to Click."**

It prints the exact indexed text view that [browser-use](https://github.com/browser-use/browser-use) sends to an LLM for a page — no API key, no model call. The point: only elements that are **interactive AND visible** get a `[N]` index. A styled `<div>` with no handler survives as plain text (unclickable), and a hidden control is dropped entirely.

Verified against `browser-use==0.13.8` (released 2026-08-16).

## Files

- `page.html` — a checkout page with one of each case: real `<button>`/`<a>`/`<input>`, a styled `<div>` with no handler, a `<div onclick>`, and a hidden `<button>`.
- `extract.py` — launches headless Chromium, loads the page, prints `dom_state.llm_representation()` and the interactive selector map.

## Setup

Requires Python 3.11+ and a Chrome/Chromium binary. Point `CHROME` in `extract.py` at your binary (the default path is the Playwright-managed Chromium used to capture the output below).

```bash
python3 -m venv venv
source venv/bin/activate
pip install browser-use            # 0.13.8 used here
```

## Run

browser-use blocks `file://` navigation by default (its SecurityWatchdog), so serve the page over localhost:

```bash
# terminal 1
python3 -m http.server 8099

# terminal 2
source venv/bin/activate
python extract.py
```

## Real captured output

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

Read the middle: `Apply discount` appears as a bare line with no `[N]` — the agent can read it but cannot target it. `Secret admin action` (the `display:none` button) does not appear at all. Indices (`19, 24, 2, 4`) are not tied to page order.

## Where this is decided in the source

- `browser_use/dom/serializer/serializer.py` — the collector guards on `if is_interactive and is_visible:` (both gates required).
- `browser_use/dom/serializer/clickable_elements.py` — interactivity heuristic: natural controls, ARIA/accessibility roles, the attribute set `{'onclick', 'onmousedown', 'onmouseup', 'onkeydown', 'onkeyup', 'tabindex'}`, or a `cursor: pointer` computed style. It does **not** detect real JS `addEventListener` handlers.

## Notes

- The script calls `get_browser_state_summary()` twice and uses the second (warmed) result. The *set* of indexed elements, the count (4), the unindexed "Apply discount", and the absent hidden button are stable across runs; the exact index of the input is not — across seven fresh runs it came back as `[2]` six times and `[3]` once, even on the warmed read. Treat indices as valid for one snapshot only.
- browser-use 0.13.x drives Chrome over the Chrome DevTools Protocol (`cdp-use`), with no Playwright dependency.

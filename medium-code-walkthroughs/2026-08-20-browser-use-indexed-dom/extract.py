"""What does a browser-use agent actually 'see' on a page?

browser-use (v0.13.x) does not hand the LLM raw HTML. It walks the live DOM,
keeps only the elements it judges interactive AND visible, and serializes them
into a compact indexed text view. Each kept element gets a [N] index the model
uses to act. Everything else is either flattened to plain text or dropped.

This script loads one local page and prints that exact view, with no LLM in the
loop, so you can see the gap between the HTML you wrote and what the agent gets.
"""

import asyncio
import os
from browser_use.browser import BrowserProfile, BrowserSession

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"  # any Chrome/Chromium works
PAGE = "http://localhost:8099/page.html"


async def main():
    session = BrowserSession(
        browser_profile=BrowserProfile(
            executable_path=CHROME,
            headless=True,
            args=["--no-sandbox"],
        )
    )
    await session.start()
    try:
        await session.navigate_to(PAGE)
        # First read warms the DOM snapshot; the second is what the agent would use.
        await session.get_browser_state_summary()
        state = await session.get_browser_state_summary()

        print("===== WHAT THE LLM SEES (dom_state.llm_representation) =====")
        print(state.dom_state.llm_representation())

        selector_map = state.dom_state.selector_map
        print("===== INTERACTIVE ELEMENTS THE AGENT CAN ACT ON =====")
        for index, node in selector_map.items():
            print(f"[{index}] <{node.tag_name} id={node.attributes.get('id', '')}>")
        print(f"total: {len(selector_map)}")
    finally:
        await session.kill()


asyncio.run(main())

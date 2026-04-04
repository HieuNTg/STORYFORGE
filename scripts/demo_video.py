"""StoryForge demo video recorder — automated UI walkthrough with Playwright.

Records a video of the full StoryForge UI: story creation form, settings,
library, reader, export, analytics, and branching pages.
Outputs: output/demo-video/demo.webm + individual screenshots.

Usage: python scripts/demo_video.py
Requires: pip install playwright && python -m playwright install chromium
"""

import asyncio
import os
from pathlib import Path

# Ensure output directory exists
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / "demo-video"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("STORYFORGE_URL", "http://localhost:7860")


async def run_demo():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(OUTPUT_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        async def screenshot(name: str):
            await page.screenshot(path=str(OUTPUT_DIR / f"{name}.png"))
            await asyncio.sleep(0.5)

        async def nav_and_capture(button_text: str, name: str, wait_ms: int = 1500):
            """Click sidebar nav button, wait, screenshot."""
            btn = page.locator(f"button:has-text('{button_text}')")
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(wait_ms / 1000)
                await screenshot(name)

        # ── 1. Homepage — Create Story ──
        await page.goto(BASE_URL)
        await asyncio.sleep(2)
        await screenshot("01-create-story-empty")

        # Fill in story form
        genre_select = page.locator("#sf-genre")
        if await genre_select.count() > 0:
            await genre_select.select_option(index=1)  # Fantasy
            await asyncio.sleep(0.5)

        title_input = page.locator("#sf-title")
        if await title_input.count() > 0:
            await title_input.fill("The Last Dragon's Heir")
            await asyncio.sleep(0.3)

        style_select = page.locator("#sf-style")
        if await style_select.count() > 0:
            await style_select.select_option(index=2)  # Intense action
            await asyncio.sleep(0.3)

        idea_input = page.locator("#sf-idea")
        if await idea_input.count() > 0:
            await idea_input.fill(
                "A young orphan discovers she is the last descendant of an ancient "
                "dragon bloodline. As dark forces rise to claim her power, she must "
                "navigate political intrigue, forbidden magic, and unlikely alliances "
                "to save a kingdom that fears her kind."
            )
            await asyncio.sleep(0.5)

        await screenshot("02-create-story-filled")

        # Show Advanced section if present
        advanced_btn = page.locator("text=Advanced")
        if await advanced_btn.count() > 0:
            await advanced_btn.first.click()
            await asyncio.sleep(1)
            await screenshot("03-advanced-options")
            # Collapse it back
            await advanced_btn.first.click()
            await asyncio.sleep(0.5)

        # ── 2. Settings page ──
        await nav_and_capture("Settings", "04-settings", 2000)

        # Scroll down to see more settings
        await page.mouse.wheel(0, 400)
        await asyncio.sleep(1)
        await screenshot("05-settings-scrolled")

        # ── 3. Library page ──
        await nav_and_capture("Library", "06-library", 1500)

        # ── 4. Reader page ──
        await nav_and_capture("Reader", "07-reader", 1500)

        # ── 5. Export page ──
        await nav_and_capture("Export", "08-export", 1500)

        # ── 6. Analytics page ──
        await nav_and_capture("Analytics", "09-analytics", 1500)

        # ── 7. Branching page ──
        await nav_and_capture("Branching", "10-branching", 1500)

        # ── 8. Guide page ──
        await nav_and_capture("Guide", "11-guide", 2000)
        await page.mouse.wheel(0, 600)
        await asyncio.sleep(1)
        await screenshot("12-guide-scrolled")

        # ── 9. Return to Create Story to show the full flow ──
        await nav_and_capture("Create Story", "13-back-to-create", 1500)

        # ── 10. Toggle dark/light mode ──
        theme_btn = page.locator("[aria-label='Switch to light mode'], [aria-label='Switch to dark mode']")
        if await theme_btn.count() > 0:
            await theme_btn.first.click()
            await asyncio.sleep(1)
            await screenshot("14-light-mode")
            # Switch back
            await theme_btn.first.click()
            await asyncio.sleep(1)

        # Final screenshot
        await screenshot("15-final")

        # Close and save video
        await context.close()
        await browser.close()

    # Find the recorded video file
    video_files = list(OUTPUT_DIR.glob("*.webm"))
    if video_files:
        latest = max(video_files, key=lambda f: f.stat().st_mtime)
        target = OUTPUT_DIR / "demo.webm"
        if latest != target:
            latest.rename(target)
        print(f"Demo video saved: {target}")
        print(f"Screenshots saved: {OUTPUT_DIR}")
    else:
        print(f"Screenshots saved: {OUTPUT_DIR}")
        print("Note: Video may not have been recorded in headed mode on some systems")


if __name__ == "__main__":
    asyncio.run(run_demo())

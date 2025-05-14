#!/usr/bin/env python3
import os
import asyncio
from playwright.async_api import async_playwright

# Enable verbose Playwright logging
os.environ["DEBUG"] = "pw:browser*"

async def debug_run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(storage_state="auth.json", viewport={"width":1000,"height":700})
        page = await context.new_page()

        page.on("console", lambda msg: print("PAGE LOG >", msg.text))
        page.on("pageerror", lambda err: print("PAGE ERROR >", err))

        print("Navigating to v0.dev in debug mode…")
        await page.goto("https://v0.dev")
        await page.wait_for_timeout(3000)

        prompt = "build me a website that shows hello world"
        print(f"Filling prompt: {prompt}")
        textarea = page.locator("textarea[placeholder='Ask v0 to build…']")
        await textarea.wait_for(state="visible")
        await textarea.fill(prompt)

        print("Submitting prompt and pausing for manual inspection…")
        btn = page.locator("button[data-testid='prompt-form-send-button']")
        await btn.wait_for(state="visible")
        await btn.click(force=True)

        # Pause to manually inspect the SPA in the open browser window
        print("Debug pause: inspect the browser window and DevTools manually. Sleeping for 5 minutes...")
        # Keep the page alive for 5 minutes (300,000 ms) so you can inspect
        await page.wait_for_timeout(300000)

        # After inspection sleep, close the browser
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_run())
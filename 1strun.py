from playwright.sync_api import sync_playwright
import time

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # Go to v0.dev and start login
    page.goto("https://v0.dev")
    page.get_by_role("link", name="Sign In").click()
    page.get_by_role("textbox", name="Work Email").fill("queuebots1@gmail.com")
    page.get_by_role("textbox", name="Work Email").press("Enter")

    # At this point, a 6-digit code is sent to your email
    print("🔐 Enter the one-time code in the browser manually.")
    print("Press Enter in this terminal when you've completed the login...")
    input()  # Wait for user to press Enter in terminal instead of page.pause()

    # After login completes and v0.dev shows your dashboard
    context.storage_state(path="auth.json")  # ✅ Save the session
    print("✅ Session saved as auth.json")

    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
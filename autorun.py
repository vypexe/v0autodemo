from playwright.sync_api import sync_playwright
import requests

def get_styled_prompt():
    r = requests.get("http://localhost:8000/interview/latest/openai")
    return r.json()["styled_prompt"]

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state="auth.json")  # 🔑 use saved login
    page = context.new_page()

    page.goto("https://v0.dev")

    page.wait_for_selector("textarea[placeholder='What do you want to build?']")
    page.fill("textarea[placeholder='What do you want to build?']", get_styled_prompt())
    page.keyboard.press("Enter")

    page.wait_for_timeout(10000)  # Wait 10s to see result
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
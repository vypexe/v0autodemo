from playwright.sync_api import sync_playwright
import json

def debug_auth_json():
    # Print the content of auth.json
    with open("auth.json", "r") as f:
        auth_data = json.load(f)
        print("Auth.json content:")
        print(json.dumps(auth_data, indent=2))
    
    # Try to use auth.json with Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set to False to see the browser
        
        # Create context with auth.json
        print("Loading auth.json into browser context...")
        context = browser.new_context(storage_state="auth.json")
        
        # Create a page and navigate to v0.dev
        page = context.new_page()
        print("Navigating to v0.dev...")
        page.goto("https://v0.dev")
        
        # Check if we're logged in
        print("Checking login status...")
        # Wait a bit for the page to load
        page.wait_for_timeout(5000)
        
        # Check for elements that indicate we're logged in
        logged_in = not page.locator("text=Sign In").is_visible()
        print(f"Logged in: {logged_in}")
        
        # Take a screenshot for verification
        page.screenshot(path="auth_debug.png")
        print("Screenshot saved as auth_debug.png")
        
        # Save the current page HTML for inspection
        html_content = page.content()
        with open("auth_debug.html", "w") as f:
            f.write(html_content)
        print("Page HTML saved as auth_debug.html")
        
        # Close browser
        context.close()
        browser.close()

if __name__ == "__main__":
    debug_auth_json()

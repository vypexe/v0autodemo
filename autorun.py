from playwright.sync_api import sync_playwright, expect
import requests
import time
import os
import sys

def get_data_from_api():
    try:
        response = requests.get("http://localhost:8000/interview/latest/openai")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching data from API: {e}")
        return None

def format_prompt(api_data):
    if not api_data:
        return "Error: Could not retrieve data from API"
    
    styled_prompt = api_data.get("styled_prompt", "")
    original_interview = api_data.get("original_interview", {})
    
    name = original_interview.get("name", "")
    initial_request = original_interview.get("initial_request", "")
    product_info = original_interview.get("product_info", "")
    website_examples = original_interview.get("website_examples", "")
    
    return f"""
{styled_prompt}

Based on the following requirements:
- Project name: {name}
- Initial request: {initial_request}
- Product information: {product_info}
- Website inspiration: {website_examples}

Please create a beautiful, professional website with a clean, modern layout, optimized for both desktop and mobile view.
"""

def run():
    print("🚀 Starting Playwright automation...")
    print("📡 Fetching data from API...")
    api_data = get_data_from_api()
    
    if not api_data:
        print("⚠️ API fetch failed. Exiting.")
        return 1
    
    prompt = format_prompt(api_data)
    print("\n--- Generated Prompt ---\n")
    print(prompt)
    print("\n------------------------\n")
    
    # Create screenshots directory if it doesn't exist
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
    
    with sync_playwright() as playwright:
        try:
            # Launch the browser with better settings
            print("🟢 Launching browser...")
            browser = playwright.chromium.launch(
                headless=False,
                slow_mo=100  # Slow down operations by 100ms for visibility
            )
            
            # Create a context with the auth file
            print("🟢 Creating browser context...")
            context = browser.new_context(storage_state="auth.json")
            
            # Create a new page
            print("🟢 Opening new page...")
            page = context.new_page()
            
            print("🌐 Navigating to https://v0.dev...")
            response = page.goto("https://v0.dev/", wait_until="domcontentloaded", timeout=15000)
            assert response is not None, "❌ Page failed to load"
            print("✅ Page loaded successfully")

            # Now continue with screenshot
            page.screenshot(path="screenshots/after_navigation.png")
            print("📸 Took screenshot after navigation")
            
            # Find and interact with the input field
            print("🔍 Looking for input field...")
            
            # Try different possible selectors - using proper expectations
            input_selectors = [
                "textarea[placeholder='Ask v0 to build…']",
                "textarea[placeholder='Ask v0 to build...']",
                "textarea",
            ]
            
            # Try each selector
            input_field = None
            for selector in input_selectors:
                try:
                    print(f"  Trying selector: {selector}")
                    locator = page.locator(selector)
                    if locator.count() > 0:
                        print(f"  ✅ Found element with selector: {selector}")
                        # Wait for it to be visible
                        expect(locator.first).to_be_visible(timeout=5000)
                        input_field = locator.first
                        break
                except Exception as e:
                    print(f"  ❌ Selector {selector} not ready: {e}")
            
            if not input_field:
                print("❌ Could not find any input element")
                # Dump the page content for debugging
                page.screenshot(path="screenshots/no_input_found.png")
                with open("screenshots/page_content.html", "w") as f:
                    f.write(page.content())
                print("📄 Dumped page content to screenshots/page_content.html")
                return 1
            
            # Fill the input with our prompt
            print("✏️ Filling input field...")
            input_field.fill(prompt)
            
            # Take screenshot after filling
            page.screenshot(path="screenshots/after_filling.png")
            print("📸 Took screenshot after filling")
            
            # Press Enter to submit
            print("⌨️ Pressing Enter...")
            input_field.press("Enter")
            
            # Wait to see the results
            print("⏱️ Waiting for generation process...")
            # We wait a bit to see the generation process
            page.wait_for_timeout(15000)
            
            # Take final screenshot
            page.screenshot(path="screenshots/final_result.png")
            print("📸 Took final screenshot")
            
            print("✅ Process completed successfully!")
            return 0
            
        except Exception as e:
            print(f"🚨 Error during automation: {e}")
            try:
                if 'page' in locals() and page:
                    page.screenshot(path="screenshots/error_screenshot.png")
                    print("📸 Took error screenshot")
            except:
                pass
            return 1
        
        finally:
            # Ensure browser cleanup
            if 'browser' in locals() and browser:
                browser.close()
                print("🏁 Browser closed")

if __name__ == "__main__":
    sys.exit(run())
from playwright.sync_api import sync_playwright, TimeoutError
import requests
import time
import os
import json

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
    # Get prompt from API
    print("Fetching prompt from API...")
    api_data = get_data_from_api()
    prompt = format_prompt(api_data)
    
    if api_data:
        print("Using generated prompt from API")
    else:
        print("API unavailable, using default prompt")
    
    # Start browser automation
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set to False to see the browser
        context = browser.new_context(storage_state="auth.json")
        page = context.new_page()

        # Create results directory
        os.makedirs("results", exist_ok=True)

        print("Navigating to v0.dev...")
        # Use a shorter timeout and domcontentloaded to avoid hanging
        page.goto("https://v0.dev", wait_until="domcontentloaded", timeout=60000)
        print("Page loaded")

        # Wait to make sure the page is interactive
        page.wait_for_timeout(3000)
        
        print("Looking for input field...")
        input_field = page.locator("textarea[placeholder='Ask v0 to build…']")
        input_field.wait_for(state="visible")
        print("Filling with prompt...")
        input_field.fill(prompt)
        
        # Instead of pressing Enter, find and click the specific submit button
        print("Looking for submit button...")
        
        # Try to find the button with the exact data-testid
        submit_button = page.locator("button[data-testid='prompt-form-send-button']")
        
        if submit_button.count() > 0:
            print("Found submit button by data-testid, clicking it...")
            submit_button.click()
        else:
            # Fallback to other methods of finding the button
            print("Submit button not found by data-testid, trying alternative methods...")
            
            # Try to find by SVG inside the button (the arrow icon)
            svg_button = page.locator("button:has(svg[data-testid='geist-icon'])")
            if svg_button.count() > 0:
                print("Found submit button by SVG icon, clicking it...")
                svg_button.click()
            else:
                # Last resort - try to use JavaScript to find and click the button
                print("Trying to click submit button using JavaScript...")
                page.evaluate("""
                    () => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const submitButton = buttons.find(button => 
                            button.innerHTML.includes('svg') && 
                            (button.getAttribute('data-testid') === 'prompt-form-send-button' || 
                             button.classList.contains('ml-1'))
                        );
                        if (submitButton) {
                            submitButton.click();
                            return true;
                        }
                        return false;
                    }
                """)
                
        print("Prompt submitted")

        try:
            # STEP 1: Wait for the initial Deploy button to appear (may take a while for generation)
            print("Waiting for Deploy button to appear (this may take several minutes)...")
            page.wait_for_selector("button:has-text('Deploy')", timeout=600000)  # 10 minute timeout
            print("Deploy button found!")
            
            # Take a screenshot before initial deployment
            timestamp = time.strftime('%Y%m%d-%H%M%S')
            page.screenshot(path=f"results/pre_deploy_{timestamp}.png")
            
            # Click the Deploy button
            deploy_button = page.locator("button:has-text('Deploy')")
            print("Clicking Deploy button...")
            deploy_button.click()
            
            # STEP 2: Wait for website generation to complete and "Deploy to Production" button to appear
            print("Waiting for website generation to complete and 'Deploy to Production' button to appear...")
            deploy_to_production_button = page.locator("button:has-text('Deploy to Production')")
            deploy_to_production_button.wait_for(state="visible", timeout=600000)  # 10 minute timeout
            print("Deploy to Production button found! Website generation completed.")
            
            # Take a screenshot before production deployment
            page.screenshot(path=f"results/pre_production_deploy_{timestamp}.png")
            
            # Wait for the Deploy to Production button to become enabled
            print("Waiting for Deploy to Production button to become enabled...")
            
            # Function to check if button is enabled
            def is_button_enabled():
                return page.evaluate("""
                    () => {
                        // Find all buttons
                        const buttons = Array.from(document.querySelectorAll('button'));
                        // Find the one with 'Deploy to Production' text content
                        const deployButton = buttons.find(button => 
                            button.textContent && button.textContent.includes('Deploy to Production')
                        );
                        
                        if (!deployButton) return false;
                        return !deployButton.disabled && !deployButton.getAttribute('aria-disabled');
                    }
                """)
            
            # Poll until button is enabled, with timeout
            max_wait_time = 600  # 10 minutes in seconds
            poll_interval = 5  # Check every 5 seconds
            start_time = time.time()
            
            button_enabled = False
            while (time.time() - start_time) < max_wait_time:
                if is_button_enabled():
                    button_enabled = True
                    break
                print("Button still disabled, waiting...")
                page.screenshot(path=f"results/waiting_for_button_{int(time.time())}.png")
                time.sleep(poll_interval)
            
            if not button_enabled:
                raise TimeoutError("Timed out waiting for Deploy to Production button to become enabled")
            
            print("Deploy to Production button is now enabled!")
            
            # Click the Deploy to Production button
            print("Clicking Deploy to Production button...")
            deploy_to_production_button.click()
            
            # STEP 3: Wait for deployment to complete and "Visit Site" button to appear
            print("Waiting for deployment to complete and Visit Site button to appear...")
            visit_site_button = page.locator("span:has-text('Visit Site')")
            visit_site_button.wait_for(state="visible", timeout=600000)  # 10 minute timeout
            print("Visit Site button found! Deployment completed successfully.")
            
            # Take a screenshot after deployment
            page.screenshot(path=f"results/post_deploy_{timestamp}.png")
            
            # STEP 4: Get the deployed site URL
            # Try to extract the URL from the link first
            deployed_url = ""
            try:
                # The Visit Site button might be inside an anchor tag with href
                url_container = page.locator("a:has(span:has-text('Visit Site'))")
                if url_container.count() > 0:
                    # Try to get the href attribute
                    deployed_url = url_container.first.get_attribute("href")
                    print(f"Extracted deployed URL: {deployed_url}")
                else:
                    # If we can't find it directly, we'll click and get the URL from the new tab
                    print("Clicking Visit Site button...")
                    with context.expect_page() as new_page_info:
                        visit_site_button.click()
                    new_page = new_page_info.value
                    new_page.wait_for_load_state("domcontentloaded")
                    deployed_url = new_page.url
                    print(f"Extracted deployed URL from new tab: {deployed_url}")
                    new_page.close()
            except Exception as e:
                print(f"Error extracting URL: {e}")
                # Just click the button as fallback
                print("Falling back to clicking Visit Site button...")
                with context.expect_page() as new_page_info:
                    visit_site_button.click()
                new_page = new_page_info.value
                new_page.wait_for_load_state("domcontentloaded")
                deployed_url = new_page.url
                print(f"Extracted deployed URL: {deployed_url}")
                new_page.close()
            
            # Save the URL to a file
            if deployed_url:
                # Create a simple results structure
                result = {
                    "timestamp": timestamp,
                    "deployed_url": deployed_url,
                    "prompt": prompt
                }
                
                # Save as JSON
                with open(f"results/deployment_{timestamp}.json", "w") as f:
                    json.dump(result, f, indent=2)
                
                # Also save to a simple text file for easy access
                with open("results/latest_deployment.txt", "w") as f:
                    f.write(f"Timestamp: {timestamp}\n")
                    f.write(f"URL: {deployed_url}\n")
                    f.write(f"Prompt Summary: {prompt[:100]}...\n")
                
                print(f"Deployment results saved to results/deployment_{timestamp}.json")
                print(f"Latest deployment URL: {deployed_url}")
            else:
                print("Could not extract deployed URL")
                
        except Exception as e:
            print(f"Error during deployment process: {e}")
            # Take a screenshot of the error state
            error_timestamp = time.strftime('%Y%m%d-%H%M%S')
            page.screenshot(path=f"results/error_{error_timestamp}.png")
        
        browser.close()

if __name__ == "__main__":
    run()
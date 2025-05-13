from playwright.sync_api import sync_playwright, TimeoutError
import requests
import time
import os
import json
import shutil
import subprocess
import sys

# Check for command-line overrides via environment variables
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
PROMPT_OVERRIDE = os.environ.get("PROMPT_OVERRIDE", None)
SKIP_SCREENSHOTS = os.environ.get("SKIP_SCREENSHOTS", "false").lower() == "true"
RESULTS_DIR = os.environ.get("RESULTS_DIR", "results")

def ensure_playwright_browsers_installed():
    """Ensure that Playwright browsers are installed"""
    print("Checking if Playwright browsers are installed...")
    try:
        # Try to run a browser check command
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("Playwright browsers installed successfully.")
        else:
            print(f"Error installing browsers: {result.stderr}")
    except Exception as e:
        print(f"Exception during browser installation: {e}")

def get_data_from_api():
    try:
        # First try the local API
        try:
            response = requests.get("http://localhost:8000/interview/latest/openai", timeout=3)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Local API unavailable: {e}")
            
        # If local API fails, try Upstash Redis
        print("Falling back to Upstash Redis...")
        
        # Get Upstash credentials from environment
        redis_url = os.environ.get("REDIS_URL")
        redis_token = os.environ.get("REDIS_TOKEN")
        
        if not redis_url or not redis_token:
            print("Upstash credentials not found in environment variables")
            return None
        
        # Import Upstash Redis client
        try:
            from upstash_redis import Redis
        except ImportError:
            print("upstash_redis library not installed. Installing...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "upstash_redis"])
                from upstash_redis import Redis
                print("Successfully installed upstash_redis")
            except Exception as install_err:
                print(f"Failed to install upstash_redis: {install_err}")
                return None
        
        # Create Redis client directly with the Upstash URL and token
        # Upstash REST API uses https:// URLs - do not modify the URL format
        print(f"Connecting to Upstash Redis using REST API...")
        
        try:
            # Use the original URL and token provided in environment variables
            redis = Redis(url=redis_url, token=redis_token)
            
            # Find all interview keys
            interview_keys = redis.keys("interview:*")
            
            if not interview_keys:
                print("No interview data found in Redis")
                return None
                
            # Sort keys by timestamp (descending) to get the most recent interview
            latest_key = sorted(interview_keys, key=lambda k: int(k.split(':')[1]), reverse=True)[0]
            print(f"Found latest interview key: {latest_key}")
            
            # Get all fields from the hash
            interview_data = redis.hgetall(latest_key)
            
            if not interview_data:
                print(f"No data found for key: {latest_key}")
                return None
                
            print(f"Successfully retrieved interview data from key: {latest_key}")
            
            # Format the data for the prompt generator
            formatted_data = {
                "original_interview": interview_data,
                "styled_prompt": ""  # Default empty styled prompt
            }
            
            return formatted_data
                
        except Exception as e:
            print(f"Error using Upstash Redis client: {e}")
            return None
                
    except Exception as e:
        print(f"Error fetching data from API: {e}")
        return None

# In autorun.py - Update the format_prompt function
def format_prompt(api_data):
    """Format the prompt for OpenAI from API data"""
    if not api_data:
        return "Error: Could not retrieve data from API"
    
    # Extract data carefully with proper error handling
    try:
        original_interview = api_data.get("original_interview", {}) or {}
        
        # Check if OpenAI API key exists
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            print("ERROR: No OpenAI API key found in environment variables")
            return "Error: OpenAI API key not configured"
            
        # Create the input data for OpenAI
        upstash_data = json.dumps(original_interview, indent=2)
        
        # Use OpenAI to create a styled, specific prompt
        try:
            import openai
            # Only use the new client API format
            client = openai.OpenAI(api_key=openai_api_key)
            
            # Send the upstash data to OpenAI for processing
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a web design expert specializing in creating detailed design prompts."},
                    {"role": "user", "content": f"Create a paragraph style prompt using this data:\n\n{upstash_data}\n\nAlign it with the project goal. Focus on specific aspects of unique style, specific font types, and design/structure as well as any unique animations that would enhance the user experience."}
                ],
                max_tokens=800
            )
            
            # Get the styled prompt from OpenAI
            styled_prompt = response.choices[0].message.content
            print("Successfully generated styled prompt with OpenAI")
            
            # Return the styled prompt directly - don't add anything else to it
            return styled_prompt.strip()
            
        except Exception as e:
            error_msg = f"Error using OpenAI API: {str(e)}"
            print(error_msg)
            return error_msg
    
    except Exception as e:
        error_msg = f"Error formatting prompt: {str(e)}"
        print(error_msg)
        return error_msg

def create_live_viewer(results_dir):
    """Create a simple HTML page that auto-refreshes to show the latest screenshot"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live v0.dev Progress Viewer</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                text-align: center;
                background-color: #f4f4f4;
            }
            h1 {
                color: #333;
            }
            .container {
                max-width: 1100px;
                margin: 0 auto;
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            .screenshot {
                max-width: 100%;
                margin-top: 20px;
                border: 1px solid #ddd;
            }
            .timestamp {
                color: #666;
                font-size: 14px;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>v0.dev Automation Progress</h1>
            <p>Live view - auto-refreshes every 2 seconds</p>
            <div class="timestamp">Last updated: <span id="timestamp"></span></div>
            <img class="screenshot" src="latest.png" alt="Latest v0.dev screenshot">
            <script>
                document.getElementById('timestamp').innerText = new Date().toLocaleString();
            </script>
        </div>
    </body>
    </html>
    """
    
    with open(os.path.join(results_dir, "live-viewer.html"), "w") as f:
        f.write(html_content)
    
    print(f"Created live viewer at {os.path.join(results_dir, 'live-viewer.html')}")
    print(f"Open this file in your browser to view live progress")

def take_screenshot(page, path, message, results_dir):
    """Take a screenshot, save it to the specified path, and also update the latest.png"""
    print(message)
    
    if SKIP_SCREENSHOTS:
        return
    
    # Take the screenshot with proper dimensions
    page.screenshot(path=path, clip={"x": 0, "y": 0, "width": 1000, "height": 700})
    
    # Also save to latest.png for live viewing
    latest_path = os.path.join(results_dir, "latest.png")
    page.screenshot(path=latest_path, clip={"x": 0, "y": 0, "width": 1000, "height": 700})
    
    # Update status file
    with open(os.path.join(results_dir, "status.txt"), "w") as f:
        f.write(f"{message}\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

def run():
    ensure_playwright_browsers_installed()
    
    # Get prompt from API or use override
    if PROMPT_OVERRIDE:
        print(f"Using prompt override from API call")
        prompt = PROMPT_OVERRIDE
    else:
        print("Fetching prompt from API...")
        api_data = get_data_from_api()
        prompt = format_prompt(api_data)
    
    if prompt:
        print("Using prompt for generation")
    else:
        print("API unavailable, using default prompt")
    
    # Create results directory and clear previous results
    results_dir = RESULTS_DIR
    print(f"Clearing previous results from {results_dir} directory...")
    clear_directory(results_dir)
    os.makedirs(results_dir, exist_ok=True)
    
    # Create live viewer HTML
    if not SKIP_SCREENSHOTS:
        create_live_viewer(results_dir)
    
    # Start browser automation
    with sync_playwright() as p:
        # Use headless mode from environment variable
        browser = p.chromium.launch(headless=HEADLESS)
        
        try:
            # Create a context with a specific viewport size
            context = browser.new_context(
                storage_state="auth.json",
                viewport={"width": 1000, "height": 700}
            )
            
            page = context.new_page()

            # Take initial screenshot
            take_screenshot(
                page, 
                os.path.join(results_dir, "00_initial.png"),
                "Starting automation process...",
                results_dir
            )

            print("Navigating to v0.dev...")
            # Use a shorter timeout and domcontentloaded to avoid hanging
            page.goto("https://v0.dev", wait_until="domcontentloaded", timeout=60000)
            print("Page loaded")

            # Take screenshot after page load
            take_screenshot(
                page, 
                os.path.join(results_dir, "01_page_loaded.png"),
                "v0.dev page loaded successfully",
                results_dir
            )

            # Wait to make sure the page is interactive
            page.wait_for_timeout(3000)
            
            # Look for input field
            print("Looking for input field...")
            input_field = page.locator("textarea[placeholder='Ask v0 to build…']")
            input_field.wait_for(state="visible")

            # Fill the prompt
            print("Filling with prompt...")
            input_field.fill(prompt)
            
            # Take screenshot after filling prompt
            take_screenshot(
                page, 
                os.path.join(results_dir, "02_prompt_filled.png"),
                "Prompt filled and ready to submit",
                results_dir
            )

            # Find and click the submit button using the data-testid
            print("Finding and clicking submit button...")
            submit_button = page.locator("button[data-testid='prompt-form-send-button']")
            submit_button.wait_for(state="visible")
            page.wait_for_timeout(1000)  # Small delay to ensure button is ready
            submit_button.click()

            print("Prompt submitted via button click")
            
            # Take screenshot after submitting
            take_screenshot(
                page, 
                os.path.join(results_dir, "03_prompt_submitted.png"),
                "Prompt submitted, waiting for generation to begin...",
                results_dir
            )

            try:
                # STEP 1: Wait for the initial Deploy button to appear (may take a while for generation)
                print("Waiting for Deploy button to appear (this may take several minutes)...")
                page.wait_for_selector("button:has-text('Deploy')", timeout=600000)  # 10 minute timeout
                print("Deploy button found!")
                
                # Take a screenshot before initial deployment
                timestamp = time.strftime('%Y%m%d-%H%M%S')
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"04_pre_deploy_{timestamp}.png"),
                    "Deploy button found! Ready to start deployment.",
                    results_dir
                )
                
                # Click the Deploy button
                deploy_button = page.locator("button:has-text('Deploy')")
                print("Clicking Deploy button...")
                deploy_button.click()
                
                # Take screenshot after clicking deploy
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"05_deploy_clicked_{timestamp}.png"),
                    "Deploy button clicked, waiting for website generation...",
                    results_dir
                )
                
                # STEP 2: Wait for website generation to complete and "Deploy to Production" button to appear
                print("Waiting for website generation to complete and 'Deploy to Production' button to appear...")
                deploy_to_production_button = page.locator("button:has-text('Deploy to Production')")
                deploy_to_production_button.wait_for(state="visible", timeout=600000)  # 10 minute timeout
                print("Deploy to Production button found! Website generation completed.")
                
                # Take a screenshot before production deployment
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"06_pre_production_deploy_{timestamp}.png"),
                    "Website generated! Deploy to Production button found.",
                    results_dir
                )
                
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
                    take_screenshot(
                        page,
                        os.path.join(results_dir, f"07_waiting_for_button_{int(time.time())}.png"),
                        f"Waiting for Deploy to Production button to become enabled... ({int((time.time() - start_time))} seconds elapsed)",
                        results_dir
                    )
                    time.sleep(poll_interval)
                
                if not button_enabled:
                    raise TimeoutError("Timed out waiting for Deploy to Production button to become enabled")
                
                print("Deploy to Production button is now enabled!")
                
                # Take screenshot of enabled button
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"08_button_enabled_{timestamp}.png"),
                    "Deploy to Production button is now enabled and ready to click!",
                    results_dir
                )
                
                # Click the Deploy to Production button
                print("Clicking Deploy to Production button...")
                deploy_to_production_button.click()
                
                # Take screenshot after clicking production deploy
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"09_production_deploy_clicked_{timestamp}.png"),
                    "Deploy to Production button clicked, waiting for deployment to complete...",
                    results_dir
                )
                
                # STEP 3: Wait for deployment to complete and "Visit Site" button to appear
                print("Waiting for deployment to complete and Visit Site button to appear...")
                visit_site_button = page.locator("span:has-text('Visit Site')")
                visit_site_button.wait_for(state="visible", timeout=600000)  # 10 minute timeout
                print("Visit Site button found! Deployment completed successfully.")
                
                # Take a screenshot after deployment
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"10_post_deploy_{timestamp}.png"),
                    "Deployment completed! Visit Site button is now available.",
                    results_dir
                )
                
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
                    with open(os.path.join(results_dir, f"deployment_{timestamp}.json"), "w") as f:
                        json.dump(result, f, indent=2)
                    
                    # Also save to a simple text file for easy access
                    with open(os.path.join(results_dir, "latest_deployment.txt"), "w") as f:
                        f.write(f"Timestamp: {timestamp}\n")
                        f.write(f"URL: {deployed_url}\n")
                        f.write(f"Prompt Summary: {prompt[:100]}...\n")
                    
                    # Update status for live viewer
                    with open(os.path.join(results_dir, "status.txt"), "w") as f:
                        f.write(f"DEPLOYMENT SUCCESSFUL!\nURL: {deployed_url}\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    print(f"Deployment results saved to {os.path.join(results_dir, f'deployment_{timestamp}.json')}")
                    print(f"Latest deployment URL: {deployed_url}")
                    
                    # For automated systems, return a success code
                    return {"status": "success", "url": deployed_url, "timestamp": timestamp}
                else:
                    print("Could not extract deployed URL")
                    return {"status": "error", "message": "Deployment completed but URL not found"}
                    
            except Exception as e:
                print(f"Error during deployment process: {e}")
                # Take a screenshot of the error state
                error_timestamp = time.strftime('%Y%m%d-%H%M%S')
                take_screenshot(
                    page,
                    os.path.join(results_dir, f"error_{error_timestamp}.png"),
                    f"ERROR: {str(e)}",
                    results_dir
                )
                return {"status": "error", "message": str(e)}
            
        except Exception as e:
            print(f"Critical error in automation: {e}")
            return {"status": "error", "message": f"Critical error: {str(e)}"}
        finally:
            # Ensure browser is closed in all scenarios
            try:
                browser.close()
            except:
                pass

def clear_directory(directory):
    """Clear all files in the specified directory except .gitkeep"""
    for item in os.listdir(directory):
        # Skip .gitkeep files
        if item == '.gitkeep':
            continue
            
        path = os.path.join(directory, item)
        try:
            if os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            print(f"Error clearing {path}: {e}")

if __name__ == "__main__":
    run()
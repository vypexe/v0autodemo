import os
import time
import subprocess
import json
import signal
import psutil
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uvicorn
from typing import Optional, Dict, Any
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import Response

app = FastAPI(title="v0.dev Automation API")

# Mount the results directory
app.mount("/results", StaticFiles(directory="results"), name="results")

# Model for request body
class AutomationRequest(BaseModel):
    prompt_override: Optional[str] = None
    headless: Optional[bool] = True
    callback_url: Optional[str] = None

# Global variables to store latest status and results
latest_status = {
    "status": "idle",
    "timestamp": None,
    "deployed_url": None,
    "error": None
}

# Dictionary to track running processes
running_processes = {}

def run_automation_task(background_tasks: BackgroundTasks, request: AutomationRequest):
    """Run the automation in a background task"""
    global latest_status, running_processes
    
    # Update status
    latest_status = {
        "status": "running", 
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "deployed_url": None,
        "error": None
    }
    
    # Create a function to run in the background
    def run_task():
        global latest_status, running_processes
        try:
            # Set environment variables for the subprocess
            env = os.environ.copy()
            if request.prompt_override:
                env["PROMPT_OVERRIDE"] = request.prompt_override
            if request.headless is not None:
                env["HEADLESS"] = str(request.headless).lower()
            
            # Add all environment variables from .env
            if os.environ.get("OPENAI_API_KEY"):
                env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
            if os.environ.get("REDIS_URL"):
                env["REDIS_URL"] = os.environ.get("REDIS_URL")
            if os.environ.get("REDIS_TOKEN"):
                env["REDIS_TOKEN"] = os.environ.get("REDIS_TOKEN")
            
            process = subprocess.Popen(
                ["python", "main_runner.py"], 
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Store the process ID
            process_id = process.pid
            running_processes[process_id] = process
            
            # Wait for process to complete or be terminated
            stdout, stderr = process.communicate()
            
            # Remove process from tracking dictionary
            if process_id in running_processes:
                del running_processes[process_id]
            
            # Check if the process was successful
            if process.returncode != 0 and latest_status["status"] != "stopped":
                latest_status["status"] = "failed"
                latest_status["error"] = stderr
                return
            
            # Skip the rest if process was manually stopped
            if latest_status["status"] == "stopped":
                return
                
            # Try to parse the output to get the deployed URL
            try:
                # Look for the results file
                results_dir = os.environ.get("RESULTS_DIR", "results")
                latest_file = os.path.join(results_dir, "latest_deployment.txt")
                
                if os.path.exists(latest_file):
                    with open(latest_file, "r") as f:
                        lines = f.readlines()
                        url = None
                        timestamp = None
                        
                        for line in lines:
                            if line.startswith("URL:"):
                                url = line.split("URL:")[1].strip()
                            if line.startswith("Timestamp:"):
                                timestamp = line.split("Timestamp:")[1].strip()
                        
                        if url:
                            latest_status["status"] = "success"
                            latest_status["deployed_url"] = url
                            if timestamp:
                                latest_status["timestamp"] = timestamp
                else:
                    latest_status["status"] = "completed_with_errors"
                    latest_status["error"] = f"[Errno 2] No such file or directory: '{latest_file}'"
            except Exception as e:
                latest_status["status"] = "completed_with_errors"
                latest_status["error"] = str(e)
            
            # If a callback URL was provided, send the results
            if request.callback_url:
                try:
                    import requests
                    requests.post(
                        request.callback_url,
                        json=latest_status,
                        headers={"Content-Type": "application/json"}
                    )
                except Exception as e:
                    print(f"Error sending callback: {e}")
                
        except Exception as e:
            latest_status["status"] = "failed"
            latest_status["error"] = str(e)
            
            # Clean up any tracked processes
            for pid in list(running_processes.keys()):
                try:
                    del running_processes[pid]
                except:
                    pass
    
    # Start the background task
    background_tasks.add_task(run_task)
    
    return {"status": "started", "message": "Automation started in background"}

@app.post("/run")
async def run_automation(request: AutomationRequest, background_tasks: BackgroundTasks):
    """Start an automation run with the provided prompt"""
    return run_automation_task(background_tasks, request)

@app.post("/run_latest")
async def run_latest(background_tasks: BackgroundTasks):
    """Start an automation run using the latest data from Upstash"""
    # Create an empty request - autorun.py will know to fetch from Upstash
    request = AutomationRequest(headless=True)
    
    # Create a function to run in the background
    def run_upstash_task():
        global latest_status
        try:
            # Update status
            latest_status = {
                "status": "running", 
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "deployed_url": None,
                "error": None
            }
            
            # Set environment variables for the subprocess
            env = os.environ.copy()
            env["USE_UPSTASH_DATA"] = "true"  # Special flag to use Upstash
            
            # Add all environment variables from .env
            if os.environ.get("OPENAI_API_KEY"):
                env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
            if os.environ.get("REDIS_URL"):
                env["REDIS_URL"] = os.environ.get("REDIS_URL")
            if os.environ.get("REDIS_TOKEN"):
                env["REDIS_TOKEN"] = os.environ.get("REDIS_TOKEN")
            
            if request.headless is not None:
                env["HEADLESS"] = str(request.headless).lower()
            
            # Execute main_runner.py
            process = subprocess.run(
                ["python", "main_runner.py"], 
                env=env,
                capture_output=True,
                text=True
            )
            
            # Check if the process was successful
            if process.returncode != 0:
                latest_status["status"] = "failed"
                latest_status["error"] = process.stderr
                return
            
            # Try to parse the output to get the deployed URL
            try:
                # Look for the results file
                results_dir = os.environ.get("RESULTS_DIR", "results")
                latest_file = os.path.join(results_dir, "latest_deployment.txt")
                
                if os.path.exists(latest_file):
                    with open(latest_file, "r") as f:
                        lines = f.readlines()
                        url = None
                        timestamp = None
                        
                        for line in lines:
                            if line.startswith("URL:"):
                                url = line.split("URL:")[1].strip()
                            if line.startswith("Timestamp:"):
                                timestamp = line.split("Timestamp:")[1].strip()
                        
                        if url:
                            latest_status["status"] = "success"
                            latest_status["deployed_url"] = url
                            if timestamp:
                                latest_status["timestamp"] = timestamp
                else:
                    latest_status["status"] = "completed_with_errors"
                    latest_status["error"] = f"[Errno 2] No such file or directory: '{latest_file}'"
            except Exception as e:
                latest_status["status"] = "completed_with_errors"
                latest_status["error"] = str(e)
            
        except Exception as e:
            latest_status["status"] = "failed"
            latest_status["error"] = str(e)
    
    # Start the background task
    background_tasks.add_task(run_upstash_task)
    
    return {"status": "started", "message": "Automation started using latest Upstash data"}

@app.get("/status")
async def get_status():
    """Get the status of the latest automation run"""
    return latest_status

@app.get("/latest")
async def get_latest():
    """Get the latest deployed URL"""
    if latest_status["deployed_url"]:
        return {
            "url": latest_status["deployed_url"],
            "timestamp": latest_status["timestamp"]
        }
    else:
        return {"message": "No deployment available yet"}

@app.get("/viewer")
async def get_live_viewer():
    """Simple HTML page to view the automation in progress"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>v0.dev Automation Viewer</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                text-align: center;
                background-color: #f5f5f5;
            }
            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
            }
            .screenshot {
                max-width: 100%;
                border: 1px solid #ddd;
                margin: 20px 0;
            }
            .info {
                margin: 20px 0;
                padding: 10px;
                background-color: #f8f8f8;
                border-radius: 4px;
                text-align: left;
            }
            .refresh-btn {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                text-align: center;
                text-decoration: none;
                display: inline-block;
                font-size: 16px;
                margin: 10px 2px;
                cursor: pointer;
                border-radius: 4px;
            }
            .timestamp {
                font-size: 14px;
                color: #666;
            }
        </style>
        <script>
            // Refresh the image every 2 seconds
            function refreshImage() {
                const img = document.getElementById('screenshotImg');
                const timestamp = new Date().getTime();
                img.src = '/latest_image?' + timestamp;
                
                // Update timestamp
                document.getElementById('timestamp').innerText = new Date().toLocaleString();
                
                // Also fetch and update status
                fetch('/status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('status').innerText = data.status;
                        
                        // If there's a deployed URL, show it
                        if (data.deployed_url) {
                            const deployedLink = document.getElementById('deployedLink');
                            deployedLink.href = data.deployed_url;
                            deployedLink.innerText = data.deployed_url;
                            document.getElementById('deployedUrlContainer').style.display = 'block';
                        }
                    })
                    .catch(error => console.error('Error fetching status:', error));
            }
            
            // Initial load and set interval
            window.onload = function() {
                refreshImage();
                setInterval(refreshImage, 2000);
            };
            
            // Manual refresh button
            function manualRefresh() {
                refreshImage();
            }
        </script>
    </head>
    <body>
        <div class="container">
            <h1>v0.dev Automation Progress</h1>
            
            <div class="info">
                <p>Current status: <strong id="status">Loading...</strong></p>
                <div id="deployedUrlContainer" style="display: none;">
                    <p>Deployed URL: <a id="deployedLink" href="#" target="_blank"></a></p>
                </div>
                <p class="timestamp">Last updated: <span id="timestamp"></span></p>
            </div>
            
            <img id="screenshotImg" class="screenshot" src="/latest_image" alt="Latest Screenshot" 
                 onerror="this.onerror=null; this.src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAfQAAAH0CAIAAABEtEjdAAAACXBIWXMAAAsTAAALEwEAmpwYAAABMklEQVR4nO3BAQEAAACCIP+vbkhAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEfUgAABRZJjdwAAAABJRU5ErkJggg=='"/>
            
            <div>
                <button class="refresh-btn" onclick="manualRefresh()">Refresh Now</button>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Add cache prevention headers
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    return Response(content=html_content, media_type="text/html", headers=headers)

@app.get("/latest_image")
async def get_latest_image():
    try:
        results_dir = os.environ.get("RESULTS_DIR", "results")
        latest_image = os.path.join(results_dir, "latest.png")
        
        # Add cache prevention headers
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        
        if os.path.exists(latest_image):
            return FileResponse(latest_image, media_type="image/png", headers=headers)
        else:
            default_image = os.path.join(results_dir, "placeholder.png")
            if os.path.exists(default_image):
                return FileResponse(default_image, media_type="image/png", headers=headers)
            
            # If no placeholder image exists, create a directory if it doesn't exist
            # and return a more informative error
            if not os.path.exists(results_dir):
                os.makedirs(results_dir, exist_ok=True)
            
            # Return a JSON response since we don't have an image to return
            return Response(
                content=json.dumps({"error": "No screenshot or placeholder image available"}),
                media_type="application/json",
                headers=headers
            )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return Response(
            content=json.dumps({"error": str(e), "details": error_details}),
            media_type="application/json"
        )

@app.get("/latest_deployment")
async def get_latest_deployment():
    """Get the raw contents of latest_deployment.txt file"""
    try:
        results_dir = os.environ.get("RESULTS_DIR", "results")
        latest_file = os.path.join(results_dir, "latest_deployment.txt")
        
        if os.path.exists(latest_file):
            with open(latest_file, "r") as f:
                content = f.read()
            return {"content": content}
        else:
            return {"error": f"File not found: {latest_file}"}
    except Exception as e:
        return {"error": str(e)}

def kill_process_tree(pid):
    """Kill a process and all its child processes"""
    try:
        # Get the main process
        parent = psutil.Process(pid)
        
        # Get all children
        children = parent.children(recursive=True)
        
        # Kill children first
        for child in children:
            try:
                child.terminate()
            except:
                pass
                
        # Wait for them to terminate
        gone, still_alive = psutil.wait_procs(children, timeout=3)
        
        # Forcefully kill any remaining children
        for process in still_alive:
            try:
                process.kill()
            except:
                pass
                
        # Kill the parent
        try:
            parent.terminate()
            parent.wait(3)
        except:
            # Force kill if still running
            try:
                parent.kill()
            except:
                pass
                
    except psutil.NoSuchProcess:
        # Process already gone
        pass
    except Exception as e:
        print(f"Error killing process tree: {e}")

@app.post("/stop")
async def stop_automation():
    """Stop the current automation run"""
    global latest_status, running_processes
    
    if latest_status["status"] == "running":
        latest_status["status"] = "stopped"
        latest_status["error"] = "Process stopped manually by user"
        
        # Terminate all running processes
        process_ids = list(running_processes.keys())
        killed_count = 0
        
        for pid in process_ids:
            try:
                # Kill the process tree (main process and all children)
                kill_process_tree(pid)
                killed_count += 1
                # Remove from tracking dictionary
                if pid in running_processes:
                    del running_processes[pid]
            except Exception as e:
                print(f"Error terminating process {pid}: {e}")
        
        return {"message": f"Automation stopped successfully. Terminated {killed_count} processes."}
    else:
        return {"message": f"No running automation to stop. Current status: {latest_status['status']}"}


@app.get("/debug")
async def debug_info():
    """Comprehensive system diagnostics combining debug and monitoring information"""
    import socket
    import platform
    import os
    import sys
    import requests
    import traceback
    import psutil
    
    # Get current time for age calculations
    current_time = time.time()
    
    debug_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "system_info": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": sys.version,
            "process_id": os.getpid(),
            "working_directory": os.getcwd(),
            "memory_usage_percent": psutil.virtual_memory().percent,
            "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
        },
        "api_status": {
            "current_status": latest_status,
            "active_processes": list(running_processes.keys()),
            "status_age_seconds": time.time() - time.mktime(time.strptime(latest_status["timestamp"], "%Y-%m-%d %H:%M:%S")) if latest_status.get("timestamp") else None
        },
        "env_vars": {
            "key_env_vars": {k: "***REDACTED***" if k in ["OPENAI_API_KEY", "REDIS_TOKEN"] else os.environ.get(k) 
                          for k in ["REDIS_URL", "REDIS_TOKEN", "HEADLESS", "PROMPT_OVERRIDE", "SKIP_SCREENSHOTS", "RESULTS_DIR", "OPENAI_API_KEY"]
                          if k in os.environ}
        },
    }
    
    # Process information
    process_info = []
    for pid in running_processes.keys():
        try:
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                process_info.append({
                    "pid": pid,
                    "status": proc.status(),
                    "cpu_percent": proc.cpu_percent(interval=0.1),
                    "memory_percent": proc.memory_percent(),
                    "create_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(proc.create_time())),
                    "running_time_seconds": current_time - proc.create_time(),
                    "cmdline": proc.cmdline()
                })
            else:
                process_info.append({
                    "pid": pid,
                    "status": "not_exists",
                    "error": "Process no longer exists but still tracked"
                })
        except Exception as e:
            process_info.append({
                "pid": pid,
                "status": "error",
                "error": str(e)
            })
    
    debug_data["processes"] = process_info
    
    # Screenshot and results directory information
    results_dir = os.environ.get("RESULTS_DIR", "results")
    debug_data["files"] = {
        "results_dir_exists": os.path.exists(results_dir),
        "auth_json_exists": os.path.exists("auth.json"),
        "auth_json_size": os.path.getsize("auth.json") if os.path.exists("auth.json") else 0,
    }
    
    # Screenshot files information
    if os.path.exists(results_dir):
        files = os.listdir(results_dir)
        debug_data["files"]["results_dir_contents"] = files
        
        # Get information about PNG files
        png_files = []
        for f in files:
            if f.endswith('.png'):
                file_path = os.path.join(results_dir, f)
                png_files.append({
                    "name": f,
                    "size_bytes": os.path.getsize(file_path),
                    "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(file_path))),
                    "age_seconds": current_time - os.path.getmtime(file_path)
                })
        
        # Sort by modification time, newest first
        png_files.sort(key=lambda x: x["age_seconds"])
        debug_data["screenshots"] = png_files
    
    # Test Upstash connectivity
    try:
        import redis
        debug_data["upstash"] = {}
        
        # Check if we have Redis URL
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            debug_data["upstash"]["error"] = "REDIS_URL environment variable not set"
        else:
            debug_data["upstash"]["url_configured"] = True
            debug_data["upstash"]["token_configured"] = bool(os.environ.get("REDIS_TOKEN"))
            
            try:
                # Try to connect to Redis
                r = redis.from_url(redis_url)
                ping_result = r.ping()
                debug_data["upstash"]["connection"] = "successful" if ping_result else "failed"
                
                # Try to get interview data
                try:
                    latest_data = r.get("latest_interview")
                    debug_data["upstash"]["latest_interview_exists"] = latest_data is not None
                    
                    if latest_data:
                        try:
                            data = json.loads(latest_data)
                            debug_data["upstash"]["data_keys"] = list(data.keys())
                            
                            # Include original_interview keys if present
                            if "original_interview" in data and isinstance(data["original_interview"], dict):
                                debug_data["upstash"]["original_interview_keys"] = list(data["original_interview"].keys())
                        except Exception as e:
                            debug_data["upstash"]["parse_error"] = str(e)
                except Exception as e:
                    debug_data["upstash"]["get_data_error"] = str(e)
            except Exception as e:
                debug_data["upstash"]["connection_error"] = str(e)
    except ImportError:
        debug_data["upstash"] = {"error": "Redis library not installed"}
    
    # Check OpenAI configuration
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    debug_data["openai"] = {
        "api_key_configured": bool(openai_api_key),
        "api_key_length": len(openai_api_key) if openai_api_key else 0
    }
    
    # Test OpenAI connectivity (if key is available)
    if openai_api_key:
        try:
            import openai
            openai.api_key = openai_api_key
            
            try:
                # Only use the new client API format
                client = openai.OpenAI(api_key=openai_api_key)
                models = client.models.list()
                debug_data["openai"]["connection"] = "successful"
                debug_data["openai"]["api_version"] = "newer OpenAI client"
                debug_data["openai"]["models_count"] = len(list(models.data)) if hasattr(models, 'data') else "unknown"
            except Exception as e:
                debug_data["openai"]["connection"] = "failed"
                debug_data["openai"]["error"] = str(e)
        except ImportError:
            debug_data["openai"]["error"] = "OpenAI library not installed"
    
    # Test format_prompt function
    try:
        from autorun import get_data_from_api, format_prompt
        api_data = get_data_from_api()
        debug_data["prompt_test"] = {
            "api_data_retrieved": api_data is not None,
            "api_data_keys": list(api_data.keys()) if api_data else None
        }
        
        if api_data:
            try:
                formatted_prompt = format_prompt(api_data)
                debug_data["prompt_test"]["format_success"] = True
                debug_data["prompt_test"]["prompt_length"] = len(formatted_prompt)
                debug_data["prompt_test"]["prompt_preview"] = formatted_prompt[:200] + "..." if len(formatted_prompt) > 200 else formatted_prompt
            except Exception as e:
                debug_data["prompt_test"]["format_error"] = str(e)
                debug_data["prompt_test"]["traceback"] = traceback.format_exc()
    except Exception as e:
        debug_data["prompt_test"] = {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    
    # Test internet connectivity
    try:
        response = requests.get("https://www.google.com", timeout=5)
        debug_data["connectivity"] = {"internet": "online" if response.status_code == 200 else "offline"}
    except Exception as e:
        debug_data["connectivity"] = {"internet": "offline", "error": str(e)}
    
    return debug_data

@app.get("/latest_image")
async def get_latest_image():
    """Serve the most recent screenshot with forced cache prevention"""
    results_dir = os.environ.get("RESULTS_DIR", "results")
    
    # Ensure results directory exists
    if not os.path.exists(results_dir):
        os.makedirs(results_dir, exist_ok=True)
        return Response(
            content=json.dumps({"error": "No screenshots available yet"}),
            media_type="application/json"
        )
    
    # Find all PNG files and sort by modification time (newest first)
    png_files = []
    for file in os.listdir(results_dir):
        if file.endswith('.png'):
            file_path = os.path.join(results_dir, file)
            png_files.append((file_path, os.path.getmtime(file_path)))
    
    # Sort by modification time, newest first
    png_files.sort(key=lambda x: x[1], reverse=True)
    
    # If there are PNG files, serve the newest one
    if png_files:
        newest_image = png_files[0][0]
        
        # Force cache prevention with strong headers
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Timestamp": str(int(time.time()))
        }
        
        # Return the newest image
        return FileResponse(newest_image, media_type="image/png", headers=headers)
    else:
        return Response(
            content=json.dumps({"error": "No screenshots available in results directory"}),
            media_type="application/json"
        )

# Added a simple welcome endpoint for testing
@app.get("/")
async def welcome():
    return {
        "message": "Welcome to v0.dev Automation API", 
        "endpoints": [
            "/run - Start automation with a prompt",
            "/run_latest - Start automation using latest Upstash data",
            "/status - Check current status",
            "/latest - Get latest deployed URL",
            "/viewer - View live automation progress",
            "/latest_deployment - Get raw deployment file",
            "/debug - Show Upstash API and system diagnostic information"
        ]
    }

if __name__ == "__main__":
    # Start the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8080)
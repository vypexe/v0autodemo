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
    try:
        # Check if the viewer file exists
        viewer_path = "results/live-viewer.html"
        if not os.path.exists(viewer_path):
            # Return a meaningful error if the file doesn't exist
            return {"error": f"Live viewer file not found at {viewer_path}. Make sure an automation has been run."}
        
        with open(viewer_path, "r") as f:
            html_content = f.read()
        
        # Add timestamp parameter to force browser to reload image
        timestamp = str(int(time.time()))
        
        # Make sure to use the absolute URL with the correct endpoint
        updated_html = html_content.replace('src="latest.png"', f'src="/latest_image?t={timestamp}"')
        
        # Add cache prevention headers
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        
        return Response(content=updated_html, media_type="text/html", headers=headers)
    except Exception as e:
        # Return a more detailed error response
        import traceback
        error_details = traceback.format_exc()
        return {"error": str(e), "details": error_details}

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
    """Provide detailed diagnostic information for troubleshooting"""
    import socket
    import platform
    import os
    import sys
    import requests
    import traceback
    
    debug_data = {
        "system_info": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": sys.version,
            "process_id": os.getpid(),
            "working_directory": os.getcwd(),
        },
        "api_status": {
            "current_status": latest_status,
            "active_processes": list(running_processes.keys())
        },
        "upstash_config": {
            "redis_url_configured": bool(os.environ.get("REDIS_URL")),
            "redis_token_configured": bool(os.environ.get("REDIS_TOKEN")),
            "redis_url_redacted": os.environ.get("REDIS_URL", "").replace("://", "://***:***@") if os.environ.get("REDIS_URL") else None,
        },
        "env_vars": {
            "key_env_vars_present": [k for k in os.environ.keys() 
                                   if k in ["REDIS_URL", "REDIS_TOKEN", "HEADLESS", "PROMPT_OVERRIDE", "SKIP_SCREENSHOTS", "RESULTS_DIR", "OPENAI_API_KEY"]]
        },
        "viewer_info": {
            "live_viewer_exists": os.path.exists("results/live-viewer.html"),
            "live_viewer_size": os.path.getsize("results/live-viewer.html") if os.path.exists("results/live-viewer.html") else 0,
            "latest_png_exists": os.path.exists("results/latest.png"),
            "latest_png_size": os.path.getsize("results/latest.png") if os.path.exists("results/latest.png") else 0,
            "latest_png_timestamp": os.path.getmtime("results/latest.png") if os.path.exists("results/latest.png") else None,
            "results_dir_contents": os.listdir("results") if os.path.exists("results") else []
        }
    }
    
    # Test Upstash connectivity
    try:
        import redis
        debug_data["upstash_test"] = {}
        
        # Check if we have Redis URL
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            debug_data["upstash_test"]["error"] = "REDIS_URL environment variable not set"
        else:
            try:
                # Try to connect to Redis
                r = redis.from_url(redis_url)
                ping_result = r.ping()
                debug_data["upstash_test"]["connection"] = "successful" if ping_result else "failed"
                
                # Try to get interview data
                try:
                    latest_data = r.get("latest_interview")
                    debug_data["upstash_test"]["latest_interview_exists"] = latest_data is not None
                    if latest_data:
                        # Just get the keys, not the actual data for privacy
                        import json
                        try:
                            data_keys = list(json.loads(latest_data).keys())
                            debug_data["upstash_test"]["latest_interview_keys"] = data_keys
                        except:
                            debug_data["upstash_test"]["latest_interview_parse_error"] = "Could not parse JSON data"
                except Exception as e:
                    debug_data["upstash_test"]["get_data_error"] = str(e)
            except Exception as e:
                debug_data["upstash_test"]["connection_error"] = str(e)
    except ImportError:
        debug_data["upstash_test"] = {"error": "Redis library not installed"}
    
    # Test internet connectivity
    try:
        response = requests.get("https://www.google.com", timeout=5)
        debug_data["connectivity"] = {"internet": "online" if response.status_code == 200 else "offline"}
    except Exception as e:
        debug_data["connectivity"] = {"internet": "offline", "error": str(e)}
    
    # Test localhost API (if that's being used)
    try:
        response = requests.get("http://localhost:8000/interview/latest/openai", timeout=2)
        debug_data["local_api"] = {
            "status_code": response.status_code,
            "working": response.status_code == 200
        }
    except Exception as e:
        debug_data["local_api"] = {"error": str(e), "working": False}
    
    # Check for auth.json file which may be needed for v0.dev
    debug_data["file_check"] = {
        "auth_json_exists": os.path.exists("auth.json"),
        "auth_json_size": os.path.getsize("auth.json") if os.path.exists("auth.json") else 0,
        "results_dir_exists": os.path.exists("results"),
    }
    
    # Check OpenAI API key
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    debug_data["openai_config"] = {
        "api_key_configured": bool(openai_api_key),
        "api_key_length": len(openai_api_key) if openai_api_key else 0,
        "api_key_prefix": openai_api_key[:4] + "..." if openai_api_key and len(openai_api_key) > 4 else None
    }
    
    # Test OpenAI connectivity (if key is available)
    if openai_api_key:
        try:
            import openai
            openai.api_key = openai_api_key
            # Try to list models - this will validate the API key
            try:
                model_list = openai.Model.list()
                debug_data["openai_test"] = {
                    "connection": "successful",
                    "models_available": len(model_list.data) > 0 if hasattr(model_list, 'data') else False
                }
            except Exception as e:
                debug_data["openai_test"] = {"connection_error": str(e)}
                
                # Try an alternative API endpoint if the main one failed
                try:
                    # Check if it's the newer API version
                    client = openai.OpenAI(api_key=openai_api_key)
                    models = client.models.list()
                    debug_data["openai_test"]["alternative_api"] = "working"
                    debug_data["openai_test"]["api_version"] = "newer OpenAI client"
                except Exception as alt_e:
                    debug_data["openai_test"]["alternative_api_error"] = str(alt_e)
        except ImportError:
            debug_data["openai_test"] = {"error": "OpenAI library not installed"}
    else:
        debug_data["openai_test"] = {"error": "OpenAI API key not configured"}
    
    # Try to get the Upstash data using the same path as in get_data_from_api
    try:
        from autorun import get_data_from_api, format_prompt
        api_data = get_data_from_api()
        debug_data["autorun_api_test"] = {
            "get_data_from_api_result": "successful" if api_data else "failed",
            "data_keys": list(api_data.keys()) if api_data else None
        }
        
        # Test the format_prompt function
        if api_data:
            try:
                formatted_prompt = format_prompt(api_data)
                debug_data["prompt_formatting"] = {
                    "success": True,
                    "prompt_length": len(formatted_prompt),
                    "prompt_preview": formatted_prompt[:100] + "..." if len(formatted_prompt) > 100 else formatted_prompt,
                    "contains_styled_prompt": "styled_prompt" in api_data and bool(api_data["styled_prompt"]),
                    "original_interview_exists": "original_interview" in api_data and bool(api_data["original_interview"])
                }
                
                # More detailed inspection of the original_interview data
                if "original_interview" in api_data and api_data["original_interview"]:
                    original_interview = api_data["original_interview"]
                    debug_data["original_interview_data"] = {
                        "has_name": "name" in original_interview and bool(original_interview["name"]),
                        "has_initial_request": "initial_request" in original_interview and bool(original_interview["initial_request"]),
                        "has_product_info": "product_info" in original_interview and bool(original_interview["product_info"]),
                        "has_website_examples": "website_examples" in original_interview and bool(original_interview["website_examples"])
                    }
            except Exception as e:
                debug_data["prompt_formatting"] = {
                    "success": False,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
    except Exception as e:
        debug_data["autorun_api_test"] = {"error": str(e), "traceback": traceback.format_exc()}
    
    return debug_data

@app.get("/latest_image")
async def get_latest_image():
    try:
        results_dir = os.environ.get("RESULTS_DIR", "results")
        latest_image = os.path.join(results_dir, "latest.png")
        
        # Add cache prevention headers - strengthen these to force browser refresh
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Image-Time": str(int(time.time()))  # Add timestamp to response headers
        }
        
        # Add debug info to log
        if os.path.exists(latest_image):
            image_age = time.time() - os.path.getmtime(latest_image)
            print(f"Serving image {latest_image}, age: {image_age:.2f} seconds")
            
            # Check if image is recent (less than 5 minutes old)
            if image_age > 300:  # 5 minutes
                print(f"WARNING: Image is older than 5 minutes ({image_age:.2f} seconds)")
            
            return FileResponse(latest_image, media_type="image/png", headers=headers)
        else:
            print(f"Image not found: {latest_image}")
            
            # Check results directory contents for debugging
            if os.path.exists(results_dir):
                files = os.listdir(results_dir)
                png_files = [f for f in files if f.endswith('.png')]
                print(f"Available PNG files in {results_dir}: {png_files}")
                
                # If there are any PNG files, serve the most recent one
                if png_files:
                    png_files.sort(key=lambda f: os.path.getmtime(os.path.join(results_dir, f)), reverse=True)
                    most_recent = os.path.join(results_dir, png_files[0])
                    print(f"Serving most recent PNG: {most_recent}")
                    return FileResponse(most_recent, media_type="image/png", headers=headers)
            else:
                print(f"Results directory not found: {results_dir}")
                os.makedirs(results_dir, exist_ok=True)
            
            # If we reach here, return a JSON response with error details
            return Response(
                content=json.dumps({
                    "error": "No screenshots available",
                    "results_dir": results_dir,
                    "exists": os.path.exists(results_dir),
                    "process_status": latest_status
                }),
                media_type="application/json",
                headers=headers
            )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error serving latest image: {str(e)}\n{error_details}")
        return Response(
            content=json.dumps({"error": str(e), "details": error_details}),
            media_type="application/json"
        )

@app.get("/monitor")
async def monitor_status():
    """Provide detailed status about the current automation run"""
    import psutil
    
    try:
        # Get current time for age calculations
        current_time = time.time()
        
        # Status information
        status_info = {
            "current_status": latest_status,
            "active_processes": list(running_processes.keys()),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # Screenshot information
        results_dir = os.environ.get("RESULTS_DIR", "results")
        latest_image = os.path.join(results_dir, "latest.png")
        
        status_info["screenshot"] = {
            "exists": os.path.exists(latest_image),
            "age_seconds": current_time - os.path.getmtime(latest_image) if os.path.exists(latest_image) else None,
            "size_bytes": os.path.getsize(latest_image) if os.path.exists(latest_image) else 0,
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
                    })
                else:
                    process_info.append({
                        "pid": pid,
                        "status": "not_exists",
                    })
            except Exception as e:
                process_info.append({
                    "pid": pid,
                    "status": "error",
                    "error": str(e)
                })
        
        status_info["processes"] = process_info
        
        # Recent activity
        if os.path.exists(results_dir):
            files = os.listdir(results_dir)
            png_files = [f for f in files if f.endswith('.png')]
            
            recent_files = []
            for png_file in sorted(png_files, key=lambda f: os.path.getmtime(os.path.join(results_dir, f)), reverse=True)[:5]:
                file_path = os.path.join(results_dir, png_file)
                recent_files.append({
                    "name": png_file,
                    "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(file_path))),
                    "age_seconds": current_time - os.path.getmtime(file_path),
                    "size_bytes": os.path.getsize(file_path),
                })
            
            status_info["recent_files"] = recent_files
        
        return status_info
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return {"error": str(e), "details": error_details}

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
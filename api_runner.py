import os
import time
import subprocess
import json
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

def run_automation_task(background_tasks: BackgroundTasks, request: AutomationRequest):
    """Run the automation in a background task"""
    global latest_status
    
    # Update status
    latest_status = {
        "status": "running", 
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "deployed_url": None,
        "error": None
    }
    
    # Create a function to run in the background
    def run_task():
        global latest_status
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
    """Serve the live-viewer.html file with updated image path"""
    try:
        # Read the template
        with open("results/live-viewer.html", "r") as f:
            html_content = f.read()
        
        # Replace the image src
        updated_html = html_content.replace('src="latest.png"', 'src="/latest_image"')
        
        # Return the modified HTML
        return Response(content=updated_html, media_type="text/html")
    except Exception as e:
        return {"error": str(e)}
    
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
            "/latest_deployment - Get raw deployment file"
        ]
    }

@app.get("/latest_image")
async def get_latest_image():
    """Serve the latest screenshot"""
    try:
        results_dir = os.environ.get("RESULTS_DIR", "results")
        latest_image = os.path.join(results_dir, "latest.png")
        
        if os.path.exists(latest_image):
            return FileResponse(latest_image)
        else:
            # Return a placeholder or default image
            default_image = os.path.join(results_dir, "placeholder.png")
            if os.path.exists(default_image):
                return FileResponse(default_image)
            return {"error": "No screenshot available yet"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Start the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8080)
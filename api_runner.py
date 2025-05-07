from fastapi import FastAPI, BackgroundTasks, HTTPException
import subprocess
import time
import os
import json
from typing import Optional, Dict, Any
from pydantic import BaseModel

# Create a FastAPI app
app = FastAPI(title="Automation API", description="API for running v0.dev automations from the cloud")

# Create a model for our automation request
class AutomationRequest(BaseModel):
    prompt_override: Optional[str] = None
    callback_url: Optional[str] = None
    headless: bool = True
    wait_for_completion: bool = False

# Global variable to store the latest automation result
latest_result = {
    "status": "idle",
    "timestamp": None,
    "deployed_url": None,
    "error": None
}

def run_automation_task(request: AutomationRequest):
    """Run the automation in a background task"""
    global latest_result
    
    try:
        latest_result = {
            "status": "running",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "deployed_url": None,
            "error": None
        }
        
        # Set environment variables for the subprocess
        env = os.environ.copy()
        if request.prompt_override:
            env["PROMPT_OVERRIDE"] = request.prompt_override
        if request.headless:
            env["HEADLESS"] = "true"
        
        # Run the autorun.py script
        process = subprocess.run(
            ["python", "autorun.py"], 
            env=env,
            capture_output=True,
            text=True
        )
        
        # Check if the process was successful
        if process.returncode != 0:
            latest_result["status"] = "failed"
            latest_result["error"] = process.stderr
            return
        
        # Try to read the deployment URL from the results
        try:
            with open("results/latest_deployment.txt", "r") as f:
                for line in f:
                    if line.startswith("URL:"):
                        deployed_url = line.strip().replace("URL:", "").strip()
                        latest_result["deployed_url"] = deployed_url
                        break
            
            latest_result["status"] = "completed"
            latest_result["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            latest_result["status"] = "completed_with_errors"
            latest_result["error"] = str(e)
        
        # Call the callback URL if provided
        if request.callback_url:
            try:
                import requests
                requests.post(
                    request.callback_url, 
                    json=latest_result,
                    headers={"Content-Type": "application/json"}
                )
            except Exception as e:
                print(f"Failed to call callback URL: {e}")
    
    except Exception as e:
        latest_result["status"] = "failed"
        latest_result["error"] = str(e)

@app.post("/run")
async def run_automation(request: AutomationRequest, background_tasks: BackgroundTasks):
    """Endpoint to run automation in the background"""
    
    # Start the automation in a background task
    background_tasks.add_task(run_automation_task, request)
    
    if request.wait_for_completion:
        # If user wants to wait, we'll poll for completion
        max_wait_time = 1800  # 30 minutes timeout
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            if latest_result["status"] in ["completed", "failed", "completed_with_errors"]:
                return latest_result
            time.sleep(2)
        
        return {"status": "timeout", "message": "Operation timed out before completion"}
    else:
        # Otherwise return immediately
        return {"status": "started", "message": "Automation started in background"}

@app.get("/status")
async def get_status():
    """Get the status of the latest automation run"""
    return latest_result

@app.get("/results/{timestamp}")
async def get_results(timestamp: str):
    """Get detailed results for a specific automation run"""
    try:
        result_path = f"results/deployment_{timestamp}.json"
        if not os.path.exists(result_path):
            raise HTTPException(status_code=404, detail="Results not found for the specified timestamp")
        
        with open(result_path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/latest")
async def get_latest_url():
    """Get just the latest deployed URL"""
    if latest_result["deployed_url"]:
        return {"url": latest_result["deployed_url"]}
    else:
        if latest_result["error"]:
            return {"error": latest_result["error"]}
        return {"message": "No deployment available yet"}

if __name__ == "__main__":
    import uvicorn
    # Run the server
    uvicorn.run("api_runner:app", host="0.0.0.0", port=8080)
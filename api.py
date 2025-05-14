from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from upstash_redis import Redis
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool

# Load environment variables from .env file
load_dotenv()

# Create FastAPI app
app = FastAPI(title="AgenticFruit API", description="API for automating first demo for AgenticFruit")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load from env
client = OpenAI()
REDIS_URL = os.getenv("REDIS_URL")
REDIS_TOKEN = os.getenv("REDIS_TOKEN")


# Validate
if not REDIS_URL.startswith("http"):
    raise ValueError("REDIS_URL must start with http:// or https://")

redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)

# Define routes
@app.get("/")
def read_root():
    return {"message": "Redis API is running"}

# Get the latest interview from redis (Upstash)
@app.get("/interview/latest")
async def get_latest_interview():
    """Get the most recent interview"""
    interview_keys = await run_in_threadpool(redis.keys, "interview:*")

    if not interview_keys:
        raise HTTPException(status_code=404, detail="No interviews found")

    # Parse keys into (key, timestamp)
    valid_keys = []
    for key in interview_keys:
        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
        try:
            prefix, ts = key_str.split(":")
            timestamp = int(ts)
            valid_keys.append((key_str, timestamp))
        except Exception:
            continue  # skip malformed keys

    if not valid_keys:
        raise HTTPException(status_code=404, detail="No valid interviews found")

    # Sort by timestamp descending
    valid_keys.sort(key=lambda x: x[1], reverse=True)
    latest_key = valid_keys[0][0]

    # Retrieve interview data
    latest_interview = await run_in_threadpool(redis.hgetall, latest_key)

    if isinstance(latest_interview, dict) and "id" not in latest_interview:
        latest_interview["id"] = latest_key

    return latest_interview


@app.get("/interview/latest/openai")
async def get_latest_interview_openai():
    """Get the latest interview and parse it through OpenAI to get an optimized styling prompt"""
    # Get the latest interview data
    latest_interview = await get_latest_interview()
    
    # Prepare the base prompt
    base_prompt = "Create a paragraph focusing on style prompt: design, font style, color scheme, animations, and blend of style/tone. It should be unique to the given info below, aligning with the goal of the user: "
    
    # Format the interview data into a string for the prompt
    interview_info = "\n".join([f"{k}: {v}" for k, v in latest_interview.items()])
    
    # Combine the base prompt with the interview info
    full_prompt = f"{base_prompt}\n\n{interview_info}"
    
    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": "You are a web design expert who specializes in creating unique and specific styling prompts that build websites using AI."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # Extract and return the styled prompt
        styled_prompt = response.choices[0].message.content
        
        return {
            "original_interview": latest_interview,
            "styled_prompt": styled_prompt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating styled prompt: {str(e)}")

@app.get("/interview/{interview_id}")
async def get_interview(interview_id: str):
    """Get interview data by ID"""
    # Check if interview exists
    if not redis.exists(f"interview:{interview_id}"):
        raise HTTPException(status_code=404, detail="Interview not found")
    
    # Get all fields of the hash
    interview_data = redis.hgetall(f"interview:{interview_id}")
    return interview_data

@app.get("/interviews")
async def get_all_interviews():
    """Get all interviews"""
    # Get all keys matching the pattern
    interview_keys = redis.keys("interview:*")
    
    result = []
    for key in interview_keys:
        interview_data = redis.hgetall(key)
        interview_data["id"] = key  # Add the key as id
        result.append(interview_data)
    
    return result

@app.get("/deployment")
async def get_latest_deployment():
    """Get the URL of the latest deployed website"""
    results_dir = os.environ.get("RESULTS_DIR", "results")
    deployment_path = os.path.join(results_dir, "latest_deployment.txt")
    
    # Check if the deployment file exists
    if not os.path.exists(deployment_path):
        return {"status": "no_deployment", "message": "No deployment has been completed yet"}
    
    try:
        # Read the deployment file
        with open(deployment_path, "r") as f:
            content = f.read().strip()
        
        # Parse the content
        lines = content.split("\n")
        deployment_data = {}
        
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                deployment_data[key.strip()] = value.strip()
        
        # Return the deployment data
        return {
            "status": "success",
            "deployment": deployment_data
        }
    except Exception as e:
        return {"status": "error", "message": f"Error reading deployment file: {str(e)}"}

@app.get("/status")
async def get_automation_status():
    """Get the current status of the automation process"""
    results_dir = os.environ.get("RESULTS_DIR", "results")
    status_path = os.path.join(results_dir, "status.txt")
    
    # Check if the status file exists
    if not os.path.exists(status_path):
        return {"status": "unknown", "message": "Status file not found"}
    
    try:
        # Read the status file
        with open(status_path, "r") as f:
            content = f.read().strip()
        
        # Return the status content
        return {
            "status": "running" if "DEPLOYMENT SUCCESSFUL" not in content else "success",
            "message": content
        }
    except Exception as e:
        return {"status": "error", "message": f"Error reading status file: {str(e)}"}

# Run with: uvicorn api:app --reload
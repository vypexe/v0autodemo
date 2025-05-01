from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from upstash_redis import Redis
from pydantic import BaseModel
import os
from dotenv import load_dotenv

from fastapi.concurrency import run_in_threadpool

# Load environment variables from .env file
load_dotenv()

# Create FastAPI app
app = FastAPI(title="AgenticFruit API", description="API for automating first demo for AgenticFruit")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production - need to update this with frontend code.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load from env
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

# Run with: uvicorn api:app --reload
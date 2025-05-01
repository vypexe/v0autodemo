from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from upstash_redis import Redis
from pydantic import BaseModel
import os
from dotenv import load_dotenv

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

# Initialize Redis connection
redis = Redis(
    url=os.getenv("REDIS_URL", "[https://inviting-trout-14302.upstash.io](https://inviting-trout-14302.upstash.io)"),
    token=os.getenv("REDIS_TOKEN", "ATfeAAIjcDFlNWNhZTQ0ZDU0ZmQ0ZWVkYWRiNzEwODhmMzQ4MTc1N3AxMA")
)

# Define routes
@app.get("/")
def read_root():
    return {"message": "Redis API is running"}

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
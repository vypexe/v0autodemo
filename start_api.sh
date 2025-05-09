#!/bin/bash

# Start the FastAPI server in the background
echo "Starting v0.dev Automation API..."
python api_runner.py &
API_PID=$!

# Wait for API to start
sleep 3

# Start ngrok in the foreground
echo "Starting ngrok tunnel..."
ngrok http 8080

# If ngrok is killed, also kill the API
kill $API_PID
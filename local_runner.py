import subprocess
import time
import sys
import os
import signal

# Global process handle for cleanup
fastapi_process = None

def start_fastapi():
    """Start the FastAPI server"""
    global fastapi_process
    print("� Launching FastAPI server...")
    fastapi_process = subprocess.Popen(["uvicorn", "api:app", "--reload"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for the server to start
    print("🔄 Waiting for FastAPI to start...")
    time.sleep(3)  # Give it a few seconds to initialize
    
    # Check if the process is still running
    if fastapi_process.poll() is not None:
        print("❌ FastAPI failed to start!")
        stdout, stderr = fastapi_process.communicate()
        print(f"STDOUT: {stdout.decode()}")
        print(f"STDERR: {stderr.decode()}")
        return False
    
    print("✅ FastAPI is live!")
    return True

def stop_fastapi():
    """Stop the FastAPI server"""
    global fastapi_process
    if fastapi_process:
        print("� Stopping FastAPI server...")
        # Try graceful shutdown first
        if os.name == 'nt':  # Windows
            fastapi_process.send_signal(signal.CTRL_C_EVENT)
        else:  # Unix/Linux/MacOS
            fastapi_process.send_signal(signal.SIGINT)
        
        # Give it a moment to shutdown gracefully
        time.sleep(2)
        
        # Force kill if still running
        if fastapi_process.poll() is None:
            fastapi_process.terminate()
            time.sleep(1)
            if fastapi_process.poll() is None:
                fastapi_process.kill()

def main():
    """Main function that runs the whole process"""
    # Start the FastAPI server
    if not start_fastapi():
        return 1
    
    try:
        # Run the Playwright automation
        print("🎬 Running Playwright automation...")
        result = subprocess.run(["python", "autorun.py"], check=False)
        return result.returncode
    
    finally:
        # Always stop the FastAPI server
        stop_fastapi()

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
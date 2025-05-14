#!/bin/bash
# setup.sh - Dependency installation script for Render.com

# Create and activate a virtual environment
python -m venv /opt/render/project/src/.venv
source /opt/render/project/src/.venv/bin/activate

# Install Python dependencies 
pip install -r requirements.txt

# Upgrade OpenAI and run migration
pip install openai --upgrade
python -m openai migrate

# Install Playwright with proper browser and dependencies
export PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright-browsers
pip install playwright==1.52.0  # Install specific version
playwright install chromium --with-deps

export DEBUG=playwright:*

echo "Setup completed successfully"
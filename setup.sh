#!/bin/bash
# setup.sh - Dependency installation script for Render.com

# Render.com already creates a virtual environment for us
# We just need to install dependencies correctly

# Install Python dependencies
pip install -r requirements.txt

# Upgrade OpenAI and run migration
pip install openai --upgrade
python -m openai migrate

# Install Playwright with proper browser and dependencies
export PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright-browsers
pip install playwright==1.40.0  # Install specific version
playwright install chromium --with-deps

echo "Setup completed successfully"
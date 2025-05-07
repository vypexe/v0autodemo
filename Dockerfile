# Use Python 3.9 slim as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium
RUN playwright install-deps chromium

# Create directory for results
RUN mkdir -p /app/results

# Copy application code
COPY . .

# Set environment variables
ENV HEADLESS=true
ENV RESULTS_DIR=/app/results
ENV PYTHONUNBUFFERED=1

# Expose port for API
EXPOSE 8080

# Create a startup script to handle auth
RUN echo '#!/bin/bash\n\
echo "$AUTH_JSON" > /app/auth.json\n\
python api_runner.py' > /app/startup.sh && chmod +x /app/startup.sh

# Start API server using the startup script
CMD ["/app/startup.sh"]
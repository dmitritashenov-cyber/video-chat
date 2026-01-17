#!/bin/bash
# Start script for Render deployment
# Render will automatically set the PORT environment variable

echo "Starting Video Chat Application..."
echo "PORT: ${PORT:-8000}"

uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info

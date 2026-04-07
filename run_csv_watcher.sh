#!/bin/bash

# CSV Watch Folder Runner
# This script starts the CSV file watcher

echo "🚀 Starting CSV Watch Folder Script"
echo "=================================="

# Create watch folder if it doesn't exist
mkdir -p ../csv_imports

# Set environment variables (customize these)
export CSV_WATCH_FOLDER="../csv_imports"
export BACKEND_URL="http://localhost:8000"

# 1. Move into the backend folder
cd backend

# 2. Activate your virtual environment (if you're using one)
source ./venv/Scripts/activate

# Run the watcher
python csv_watcher.py
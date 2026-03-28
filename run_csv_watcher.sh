#!/bin/bash

# CSV Watch Folder Runner
# This script starts the CSV file watcher

echo "🚀 Starting CSV Watch Folder Script"
echo "=================================="

# Create watch folder if it doesn't exist
mkdir -p ./csv_imports

# Set environment variables (customize these)
export CSV_WATCH_FOLDER="./csv_imports"
export BACKEND_URL="http://localhost:8000"

# Run the watcher
python3 csv_watcher.py
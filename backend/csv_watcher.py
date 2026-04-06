#!/usr/bin/env python3
"""
CSV Watch Folder Script
Monitors a folder for new CSV files and automatically uploads them to the backend
"""

import os
import time
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import logging

# Configuration
WATCH_FOLDER = os.getenv('CSV_WATCH_FOLDER', './csv_imports')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
PROCESSED_FOLDER = os.path.join(WATCH_FOLDER, 'processed')
FAILED_FOLDER = os.path.join(WATCH_FOLDER, 'failed')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CSVHandler(FileSystemEventHandler):
    """Handler for CSV file events"""
    
    def __init__(self):
        self.processed_files = set()
    
    def on_created(self, event):
        """Called when a file is created in the watch folder"""
        if event.is_directory:
            return
        
        filepath = event.src_path
        
        # Only process CSV files
        if not filepath.lower().endswith('.csv'):
            return
        
        # Avoid processing the same file multiple times
        if filepath in self.processed_files:
            return
        
        # Wait a moment to ensure file is fully written
        time.sleep(1)
        
        self.process_csv(filepath)
    
    def process_csv(self, filepath):
        """Upload CSV to backend"""
        logger.info(f"Processing new CSV: {filepath}")
        
        try:
            # Read the file
            with open(filepath, 'rb') as f:
                files = {'file': (os.path.basename(filepath), f, 'text/csv')}
                
                # Upload to backend
                response = requests.post(
                    f"{BACKEND_URL}/api/upload-csv",
                    files=files,
                    timeout=30
                )
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Success: Parsed {result['count']} transactions from {os.path.basename(filepath)}")
                
                # Move to processed folder
                self.move_to_processed(filepath)
                self.processed_files.add(filepath)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to upload {os.path.basename(filepath)}: {str(e)}")
            self.move_to_failed(filepath, str(e))
        except Exception as e:
            logger.error(f"❌ Error processing {os.path.basename(filepath)}: {str(e)}")
            self.move_to_failed(filepath, str(e))
    
    def move_to_processed(self, filepath):
        """Move successfully processed file to processed folder"""
        try:
            os.makedirs(PROCESSED_FOLDER, exist_ok=True)
            filename = os.path.basename(filepath)
            dest = os.path.join(PROCESSED_FOLDER, filename)
            
            # If file exists, add timestamp
            if os.path.exists(dest):
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                name, ext = os.path.splitext(filename)
                dest = os.path.join(PROCESSED_FOLDER, f"{name}_{timestamp}{ext}")
            
            os.rename(filepath, dest)
            logger.info(f"Moved to: {dest}")
        except Exception as e:
            logger.error(f"Failed to move file: {str(e)}")
    
    def move_to_failed(self, filepath, error):
        """Move failed file to failed folder"""
        try:
            os.makedirs(FAILED_FOLDER, exist_ok=True)
            filename = os.path.basename(filepath)
            dest = os.path.join(FAILED_FOLDER, filename)
            
            # If file exists, add timestamp
            if os.path.exists(dest):
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                name, ext = os.path.splitext(filename)
                dest = os.path.join(FAILED_FOLDER, f"{name}_{timestamp}{ext}")
            
            os.rename(filepath, dest)
            
            # Write error log
            error_log = dest + '.error.txt'
            with open(error_log, 'w') as f:
                f.write(f"Error processing file: {filename}\n")
                f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Error: {error}\n")
            
            logger.info(f"Moved to failed folder: {dest}")
        except Exception as e:
            logger.error(f"Failed to move file to failed folder: {str(e)}")

def process_existing_files(handler):
    """Process any CSV files that already exist in the watch folder"""
    logger.info(f"Checking for existing CSV files in {WATCH_FOLDER}")
    
    if not os.path.exists(WATCH_FOLDER):
        os.makedirs(WATCH_FOLDER)
        logger.info(f"Created watch folder: {WATCH_FOLDER}")
        return
    
    csv_files = [f for f in os.listdir(WATCH_FOLDER) 
                 if f.lower().endswith('.csv') and os.path.isfile(os.path.join(WATCH_FOLDER, f))]
    
    if csv_files:
        logger.info(f"Found {len(csv_files)} existing CSV file(s)")
        for filename in csv_files:
            filepath = os.path.join(WATCH_FOLDER, filename)
            handler.process_csv(filepath)
    else:
        logger.info("No existing CSV files found")

def main():
    """Main function to start the file watcher"""
    logger.info("=" * 60)
    logger.info("CSV Watch Folder Script Started")
    logger.info("=" * 60)
    logger.info(f"Watch Folder: {WATCH_FOLDER}")
    logger.info(f"Backend URL: {BACKEND_URL}")
    logger.info(f"Processed Folder: {PROCESSED_FOLDER}")
    logger.info(f"Failed Folder: {FAILED_FOLDER}")
    logger.info("=" * 60)
    
    # Ensure watch folder exists
    os.makedirs(WATCH_FOLDER, exist_ok=True)
    
    # Create event handler
    event_handler = CSVHandler()
    
    # Process existing files first
    process_existing_files(event_handler)
    
    # Create observer
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()
    
    logger.info("🔍 Watching for new CSV files... (Press Ctrl+C to stop)")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n⏹️  Stopping file watcher...")
        observer.stop()
    
    observer.join()
    logger.info("✅ File watcher stopped")

if __name__ == "__main__":
    main()
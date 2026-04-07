#!/usr/bin/env python3
"""
CSV Watch Folder Script
Monitors a folder for new CSV files and automatically uploads them to the backend
"""

import os
import shutil
import time
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
import logging

# Configuration
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
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

        if not filepath.lower().endswith('.csv'):
            return

        if filepath in self.processed_files:
            return

        # Wait a moment to ensure file is fully written
        time.sleep(1)

        self.process_csv(filepath)

    def process_csv(self, filepath):
        """Upload CSV to backend, then move to processed or failed folder"""
        logger.info(f"Processing new CSV: {filepath}")

        try:
            # Keep the with-block tight — close the handle before moving (critical on Windows)
            with open(filepath, 'rb') as f:
                files = {'file': (os.path.basename(filepath), f, 'text/csv')}
                response = requests.post(
                    f"{BACKEND_URL}/api/upload-csv",
                    files=files,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()

            # File handle is now closed — safe to move on all platforms
            logger.info(f"Success: Parsed {result['count']} transactions from {os.path.basename(filepath)}")
            self.move_to_processed(filepath)
            self.processed_files.add(filepath)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to upload {os.path.basename(filepath)}: {str(e)}")
            self.move_to_failed(filepath, str(e))
        except Exception as e:
            logger.error(f"Error processing {os.path.basename(filepath)}: {str(e)}")
            self.move_to_failed(filepath, str(e))

    # ------------------------------------------------------------------
    # File movement helpers
    # ------------------------------------------------------------------

    def _move_file(self, filepath: str, dest_folder: str) -> str:
        """
        Copy filepath into dest_folder and remove the original.

        Uses copy+delete instead of os.rename so it works across drives
        and avoids Windows file-lock errors. Appends a timestamp to the
        filename if a file with the same name already exists in dest_folder.

        Returns the final destination path.
        """
        os.makedirs(dest_folder, exist_ok=True)
        filename = os.path.basename(filepath)
        dest = os.path.join(dest_folder, filename)

        if os.path.exists(dest):
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            name, ext = os.path.splitext(filename)
            dest = os.path.join(dest_folder, f"{name}_{timestamp}{ext}")

        shutil.copy2(filepath, dest)
        os.remove(filepath)
        return dest

    def move_to_processed(self, filepath: str):
        """Move a successfully processed file to the processed folder"""
        try:
            dest = self._move_file(filepath, PROCESSED_FOLDER)
            logger.info(f"Moved to processed: {dest}")
        except Exception as e:
            logger.error(f"Failed to move file to processed folder: {str(e)}")

    def move_to_failed(self, filepath: str, error: str):
        """Move a failed file to the failed folder and write an error log alongside it"""
        try:
            dest = self._move_file(filepath, FAILED_FOLDER)

            error_log = dest + '.error.txt'
            with open(error_log, 'w') as f:
                f.write(f"Error processing file: {os.path.basename(filepath)}\n")
                f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Error: {error}\n")

            logger.info(f"Moved to failed: {dest}")
        except Exception as e:
            logger.error(f"Failed to move file to failed folder: {str(e)}")


def process_existing_files(handler: CSVHandler):
    """Process any CSV files already sitting in the watch folder at startup"""
    logger.info(f"Checking for existing CSV files in {WATCH_FOLDER}")

    if not os.path.exists(WATCH_FOLDER):
        os.makedirs(WATCH_FOLDER)
        logger.info(f"Created watch folder: {WATCH_FOLDER}")
        return

    csv_files = [
        f for f in os.listdir(WATCH_FOLDER)
        if f.lower().endswith('.csv') and os.path.isfile(os.path.join(WATCH_FOLDER, f))
    ]

    if csv_files:
        logger.info(f"Found {len(csv_files)} existing CSV file(s)")
        for filename in csv_files:
            handler.process_csv(os.path.join(WATCH_FOLDER, filename))
    else:
        logger.info("No existing CSV files found")


def main():
    """Main function to start the file watcher"""
    logger.info("=" * 60)
    logger.info("CSV Watch Folder Script Started")
    logger.info("=" * 60)
    logger.info(f"Watch Folder:      {WATCH_FOLDER}")
    logger.info(f"Backend URL:       {BACKEND_URL}")
    logger.info(f"Processed Folder:  {PROCESSED_FOLDER}")
    logger.info(f"Failed Folder:     {FAILED_FOLDER}")
    logger.info("=" * 60)

    os.makedirs(WATCH_FOLDER, exist_ok=True)

    event_handler = CSVHandler()
    process_existing_files(event_handler)

    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()

    logger.info("Watching for new CSV files... (Press Ctrl+C to stop)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping file watcher...")
        observer.stop()

    observer.join()
    logger.info("File watcher stopped")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
CSV Watch Folder Script
Monitors a folder for new CSV files and automatically uploads them to the backend.
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
PROCESSED_LOG = os.path.join(PROCESSED_FOLDER, '.processed_log')

MAX_RETRIES = 3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def _wait_for_file_stable(filepath: str, poll_interval: float = 0.2, timeout: float = 5.0) -> bool:
    """Return True when the file size stops changing; False if the file never stabilises.

    Polls every *poll_interval* seconds and considers the file ready when its size
    is the same on two consecutive reads.  Falls back to False after *timeout* seconds
    so callers are never stuck indefinitely.
    """
    deadline = time.monotonic() + timeout
    prev_size = -1
    while time.monotonic() < deadline:
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return False
        if size == prev_size and size > 0:
            return True
        prev_size = size
        time.sleep(poll_interval)
    return False


class CSVHandler(FileSystemEventHandler):
    """Handler for CSV file system events."""

    def __init__(self):
        self.processed_files: set = self._load_processed_log()

    # ------------------------------------------------------------------
    # Processed-log persistence
    # ------------------------------------------------------------------

    def _load_processed_log(self) -> set:
        """Load the set of already-processed file paths from disk."""
        if not os.path.exists(PROCESSED_LOG):
            return set()
        with open(PROCESSED_LOG) as f:
            return {line.strip() for line in f if line.strip()}

    def _record_processed(self, filepath: str):
        """Append *filepath* to the on-disk log and the in-memory set."""
        os.makedirs(PROCESSED_FOLDER, exist_ok=True)
        with open(PROCESSED_LOG, 'a') as f:
            f.write(filepath + '\n')
        self.processed_files.add(filepath)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def on_created(self, event):
        """Called when a file is created in the watch folder."""
        if event.is_directory:
            return

        filepath = event.src_path

        if not filepath.lower().endswith('.csv'):
            return

        if filepath in self.processed_files:
            logger.info(f"Skipping already-processed file: {filepath}")
            return

        # Wait until the file has finished writing before touching it
        if not _wait_for_file_stable(filepath):
            logger.warning(
                f"File did not stabilise within 5 s, skipping: {filepath}"
            )
            return

        self.process_csv(filepath)

    # ------------------------------------------------------------------
    # Upload with retry
    # ------------------------------------------------------------------

    def process_csv(self, filepath: str):
        """Upload CSV to backend with exponential-backoff retries, then move it."""
        logger.info(f"Processing new CSV: {filepath}")

        last_error: str = ""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with open(filepath, 'rb') as f:
                    files = {'file': (os.path.basename(filepath), f, 'text/csv')}
                    response = requests.post(
                        f"{BACKEND_URL}/api/upload-csv",
                        files=files,
                        timeout=30,
                    )
                    response.raise_for_status()
                    result = response.json()

                logger.info(
                    f"Success: Parsed {result['count']} transactions "
                    f"from {os.path.basename(filepath)}"
                )
                self.move_to_processed(filepath)
                self._record_processed(filepath)
                return  # done

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                wait = 2 ** (attempt - 1)  # 1 s, 2 s, 4 s
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"Attempt {attempt}/{MAX_RETRIES} failed for "
                        f"{os.path.basename(filepath)}, retrying in {wait}s: {e}"
                    )
                    time.sleep(wait)
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error processing {os.path.basename(filepath)}: {e}")
                break  # non-recoverable, go straight to failed

        logger.error(
            f"All {MAX_RETRIES} attempts failed for {os.path.basename(filepath)}: {last_error}"
        )
        self.move_to_failed(filepath, last_error)

    # ------------------------------------------------------------------
    # File movement helpers
    # ------------------------------------------------------------------

    def _move_file(self, filepath: str, dest_folder: str) -> str:
        """Copy *filepath* into *dest_folder* then delete the original.

        Uses copy+delete instead of os.rename so it works across drives and
        avoids Windows file-lock errors.  Appends a timestamp to the filename
        when a file with the same name already exists in *dest_folder*.

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
        """Move a successfully processed file to the processed folder."""
        try:
            dest = self._move_file(filepath, PROCESSED_FOLDER)
            logger.info(f"Moved to processed: {dest}")
        except Exception as e:
            logger.error(f"Failed to move file to processed folder: {str(e)}")

    def move_to_failed(self, filepath: str, error: str):
        """Move a failed file to the failed folder and write an error log alongside it."""
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
    """Process any CSV files already sitting in the watch folder at startup."""
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
            filepath = os.path.join(WATCH_FOLDER, filename)
            if filepath in handler.processed_files:
                logger.info(f"Skipping already-processed file: {filename}")
                continue
            handler.process_csv(filepath)
    else:
        logger.info("No existing CSV files found")


def main():
    """Main function to start the file watcher."""
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

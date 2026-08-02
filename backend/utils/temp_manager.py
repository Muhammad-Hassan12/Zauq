import os
import time
import asyncio
import logging

logger = logging.getLogger("zauq.temp_manager")

class TempFileManager:
    def __init__(self, max_age_seconds: int = 300):
        self.max_age_seconds = max_age_seconds
        self.tracked_files = set()

    def register(self, filepath: str):
        if filepath and os.path.exists(filepath):
            self.tracked_files.add(filepath)

    async def cleanup_loop(self, interval_seconds: int = 60):
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                now = time.time()
                to_remove = set()
                for filepath in list(self.tracked_files):
                    if not os.path.exists(filepath):
                        to_remove.add(filepath)
                        continue
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > self.max_age_seconds:
                        try:
                            os.remove(filepath)
                            logger.info(f"Cleaned up temp file: {filepath}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up temp file {filepath}: {e}")
                        to_remove.add(filepath)
                self.tracked_files -= to_remove
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in temp file cleanup loop: {e}")

temp_file_manager = TempFileManager()

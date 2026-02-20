"""
File handler module for recording management and uploads.
Handles Telegram direct upload and GoFile integration.
"""

import os
import logging
import requests
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Constants
TELEGRAM_MAX_FILE_SIZE = 4.2 * 1024 * 1024 * 1024  # 4.2 GB
GOFILE_API = "https://api.gofile.io"


class FileHandler:
    """Handle file operations and uploads."""
    
    def __init__(self, recordings_dir: str = "./recordings"):
        self.recordings_dir = recordings_dir
        Path(self.recordings_dir).mkdir(parents=True, exist_ok=True)
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        try:
            return os.path.getsize(file_path)
        except OSError as e:
            logger.error(f"Error getting file size: {e}")
            return 0
    
    def get_file_size_mb(self, file_path: str) -> float:
        """Get file size in MB."""
        return self.get_file_size(file_path) / (1024 * 1024)
    
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(file_path) and os.path.isfile(file_path)
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file."""
        try:
            if self.file_exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False
    
    def is_file_too_large(self, file_path: str, max_size_bytes: int = TELEGRAM_MAX_FILE_SIZE) -> bool:
        """Check if file exceeds maximum size."""
        return self.get_file_size(file_path) > max_size_bytes
    
    async def upload_to_gofile(self, file_path: str, token: str) -> Optional[Tuple[bool, str]]:
        """
        Upload file to GoFile.
        Returns: (success, download_url_or_error_message)
        """
        if not self.file_exists(file_path):
            return False, "File does not exist"
        
        try:
            logger.info(f"Uploading to GoFile: {file_path}")
            
            # Get the best server
            try:
                servers_response = requests.get(f"{GOFILE_API}/servers", timeout=10)
                servers_response.raise_for_status()
                servers_data = servers_response.json()
                
                if servers_data.get("status") != "ok":
                    return False, "Failed to get GoFile servers"
                
                server = servers_data["data"]["servers"][0]["name"]
            except Exception as e:
                logger.error(f"Error getting GoFile server: {e}")
                return False, "Failed to connect to GoFile"
            
            # Upload file
            upload_url = f"https://{server}.gofile.io/uploadFile"
            
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {'token': token}
                
                response = requests.post(upload_url, files=files, data=data, timeout=300)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("status") != "ok":
                    error = result.get("data", {}).get("error", "Unknown error")
                    logger.error(f"GoFile upload failed: {error}")
                    return False, f"Upload failed: {error}"
                
                file_id = result["data"]["fileId"]
                download_url = f"https://gofile.io/d/{file_id}"
                
                logger.info(f"Successfully uploaded to GoFile: {download_url}")
                return True, download_url
        
        except requests.exceptions.Timeout:
            return False, "GoFile upload timeout"
        except Exception as e:
            logger.error(f"Error uploading to GoFile: {e}")
            return False, f"Upload error: {str(e)}"
    
    def create_recording_filename(self, prefix: str = "SONY YAY! SonyLIV Recording") -> str:
        """Create a unique recording filename."""
        timestamp = Path.stat(Path(self.recordings_dir)).st_mtime if os.path.exists(self.recordings_dir) else 0
        return os.path.join(self.recordings_dir, f"{prefix}.mkv")
    
    def cleanup_old_recordings(self, max_age_hours: int = 24) -> int:
        """
        Clean up old recording files.
        Returns: number of files deleted.
        """
        import time
        
        deleted_count = 0
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        try:
            for file_path in Path(self.recordings_dir).glob("*.mkv"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        if self.delete_file(str(file_path)):
                            deleted_count += 1
        except Exception as e:
            logger.error(f"Error cleaning up old recordings: {e}")
        
        return deleted_count


class ConcurrentRecordingManager:
    """Manage concurrent recording operations."""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.active_recordings: dict = {}  # user_id -> recording_info
        self.recording_semaphore = None
    
    async def initialize(self):
        """Initialize the semaphore."""
        from asyncio import Semaphore
        self.recording_semaphore = Semaphore(self.max_concurrent)
    
    async def acquire(self, user_id: int) -> bool:
        """Try to start a new recording for user."""
        if not self.recording_semaphore:
            raise RuntimeError("Recording manager not initialized")
        
        if user_id in self.active_recordings:
            return False
        
        if self.get_active_count() >= self.max_concurrent:
            return False
        
        await self.recording_semaphore.acquire()
        self.active_recordings[user_id] = {"start_time": None}
        return True
    
    async def release(self, user_id: int):
        """Release recording slot for user."""
        if user_id in self.active_recordings:
            del self.active_recordings[user_id]
        
        if self.recording_semaphore:
            self.recording_semaphore.release()
    
    def get_active_count(self) -> int:
        """Get number of active recordings."""
        return len(self.active_recordings)
    
    def get_remaining_slots(self) -> int:
        """Get number of available recording slots."""
        return self.max_concurrent - self.get_active_count()
    
    def is_user_recording(self, user_id: int) -> bool:
        """Check if user has active recording."""
        return user_id in self.active_recordings


# Global instances
file_handler = None
recording_manager = None


def initialize_handlers(recordings_dir: str = "./recordings", max_concurrent: int = 3):
    """Initialize global handler instances."""
    global file_handler, recording_manager
    file_handler = FileHandler(recordings_dir)
    recording_manager = ConcurrentRecordingManager(max_concurrent)
    return file_handler, recording_manager

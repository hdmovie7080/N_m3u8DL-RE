"""
Recording module for SONY YAY! SonyLIV Recording Bot.
Handles both ffmpeg and N_m3u8DL-RE recording methods.
"""

import asyncio
import subprocess
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)


class RecorderBase:
    """Base class for recording implementations."""
    
    def __init__(self, stream_url: str, duration: str, output_path: str):
        self.stream_url = stream_url
        self.duration = duration  # HH:MM:SS format
        self.output_path = output_path
        self.process: Optional[subprocess.Popen] = None
        self.start_time: Optional[float] = None
        self.cancelled = False
        
    def parse_duration(self) -> int:
        """Parse HH:MM:SS format to seconds."""
        try:
            parts = self.duration.split(':')
            if len(parts) != 3:
                raise ValueError("Invalid format")
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid duration format: {self.duration}. Use HH:MM:SS")
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current recording progress (0-100%)."""
        if not self.start_time or not self.process:
            return {"percent": 0, "elapsed": "00:00:00"}
        
        total_seconds = self.parse_duration()
        elapsed = time.time() - self.start_time
        percent = min(int((elapsed / total_seconds) * 100), 100)
        
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        return {
            "percent": percent,
            "elapsed": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "total": self.duration,
            "running": self.process.poll() is None
        }
    
    async def cancel(self):
        """Cancel the recording."""
        self.cancelled = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                await asyncio.sleep(2)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception as e:
                logger.error(f"Error cancelling process: {e}")
    
    async def record(self, progress_callback: Optional[Callable] = None) -> bool:
        """Start recording. Override in subclasses."""
        raise NotImplementedError


class FFmpegRecorder(RecorderBase):
    """FFmpeg-based recorder."""
    
    async def record(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        Record using ffmpeg with the specified command.
        Command: ffmpeg -nostdin -rw_timeout 15000000 -i {stream_url} 
                 -map p:7 -map_metadata 0 -map -0:d -c copy -t {duration} -y {output}
        """
        try:
            # Ensure output directory exists
            Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Build ffmpeg command
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-rw_timeout", "15000000",
                "-i", self.stream_url,
                "-map", "p:7",
                "-map_metadata", "0",
                "-map", "-0:d",
                "-c", "copy",
                "-t", self.duration,
                "-y",
                self.output_path
            ]
            
            logger.info(f"Starting FFmpeg recording: {' '.join(cmd[:5])}...")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.start_time = time.time()
            
            # Monitor process
            while True:
                if self.cancelled:
                    await self.cancel()
                    return False
                
                # Check if process is still running
                poll_result = self.process.poll()
                if poll_result is not None:
                    # Process finished
                    if poll_result == 0:
                        logger.info(f"FFmpeg recording completed successfully: {self.output_path}")
                        return True
                    else:
                        stderr = self.process.stderr.read() if self.process.stderr else "Unknown error"
                        logger.error(f"FFmpeg failed with code {poll_result}: {stderr}")
                        return False
                
                # Send progress update if callback provided
                if progress_callback:
                    progress = self.get_progress()
                    try:
                        await asyncio.to_thread(progress_callback, progress)
                    except Exception as e:
                        logger.error(f"Error in progress callback: {e}")
                
                # Wait before checking again
                await asyncio.sleep(2)
        
        except Exception as e:
            logger.error(f"FFmpeg recording error: {e}")
            return False
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()


class N_m3u8DLRecorder(RecorderBase):
    """N_m3u8DL-RE based recorder."""
    
    async def record(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        Record using N_m3u8DL-RE.
        Command: N_m3u8DL-RE.exe {stream_url} -o {output_dir} --save-name {filename} 
                 --max-time {duration}
        """
        try:
            # Ensure output directory exists
            output_dir = Path(self.output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            filename = Path(self.output_path).stem
            
            # Build N_m3u8DL-RE command
            cmd = [
                "N_m3u8DL-RE",
                self.stream_url,
                "-o", str(output_dir),
                "--save-name", filename,
                "--max-time", self.duration,
                "-M", "mp4:H.264"
            ]
            
            logger.info(f"Starting N_m3u8DL-RE recording: {' '.join(cmd[:3])}...")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            self.start_time = time.time()
            
            # Monitor process with output parsing
            while True:
                if self.cancelled:
                    await self.cancel()
                    return False
                
                # Check if process is still running
                poll_result = self.process.poll()
                if poll_result is not None:
                    # Process finished
                    if poll_result == 0:
                        # Check if output file exists
                        if os.path.exists(self.output_path):
                            logger.info(f"N_m3u8DL-RE recording completed: {self.output_path}")
                            return True
                        else:
                            logger.error(f"Output file not created: {self.output_path}")
                            return False
                    else:
                        stderr = self.process.stderr.read() if self.process.stderr else "Unknown error"
                        logger.error(f"N_m3u8DL-RE failed with code {poll_result}: {stderr}")
                        return False
                
                # Send progress update if callback provided
                if progress_callback:
                    progress = self.get_progress()
                    try:
                        await asyncio.to_thread(progress_callback, progress)
                    except Exception as e:
                        logger.error(f"Error in progress callback: {e}")
                
                # Wait before checking again
                await asyncio.sleep(2)
        
        except Exception as e:
            logger.error(f"N_m3u8DL-RE recording error: {e}")
            return False
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()


class RecorderFactory:
    """Factory for creating recorder instances."""
    
    @staticmethod
    def create(method: str, stream_url: str, duration: str, output_path: str) -> RecorderBase:
        """Create a recorder instance based on method."""
        if method.lower() == "ffmpeg":
            return FFmpegRecorder(stream_url, duration, output_path)
        elif method.lower() == "n_m3u8dl":
            return N_m3u8DLRecorder(stream_url, duration, output_path)
        else:
            raise ValueError(f"Unknown recording method: {method}")

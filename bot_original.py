import asyncio
import os
import json
import logging
import time
import re
import sys
import signal
import subprocess
import math
import shutil
import uuid
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set, List, Tuple, Union
from urllib.parse import urlparse, quote
from pathlib import Path

import aiofiles
import pymongo
from pyrogram import Client, filters, __version__, idle
from pyrogram.types import (
    InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, BotCommand, ForceReply
)
from pyrogram.errors import FloodWait, MessageNotModified, BadRequest
from pyrogram.enums import ParseMode
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
DB_URL = os.getenv("DB_URL", "")
DB_NAME = os.getenv("DB_NAME", "m3u8_bot")
SHORTLINK_API_TOKEN = os.getenv("SHORTLINK_API_TOKEN", "")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "./downloads")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
MAX_CONCURRENT_RECORDINGS = int(os.getenv("MAX_CONCURRENT_RECORDINGS", "3"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "4096"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

def get_ffprobe_path():
    """Get ffprobe path, trying common locations."""
    ffprobe_candidates = [
        "ffprobe",
        "/usr/bin/ffprobe",
        "/usr/local/bin/ffprobe",
        shutil.which("ffprobe")
    ]
    for candidate in ffprobe_candidates:
        if candidate and (candidate == "ffprobe" or os.path.exists(candidate)):
            return candidate
    return "ffprobe"

FFPROBE_PATH = get_ffprobe_path()

# Set timezone to Asia/Kolkata
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
    def get_ist_time():
        # Return naive datetime for consistent comparisons
        return datetime.now(IST).replace(tzinfo=None)
except ImportError:
    # Fallback if pytz is not available
    IST_OFFSET = timedelta(hours=5, minutes=30)
    def get_ist_time():
        return datetime.now(timezone.utc).replace(tzinfo=None) + IST_OFFSET

# Validate required configuration
if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
    logging.error("Missing required configuration. Please check your .env file.")
    sys.exit(1)

# --- Language Mapping ---
LANGUAGE_MAPPING = {
    "hindi": "HIN",
    "assamese": "ASM",
    "bengali": "BEN",
    "bodo": "BOD",
    "dogri": "DOG",
    "gujarati": "GUJ",
    "kannada": "KAN",
    "kashmiri": "KAS",
    "konkani": "KON",
    "maithili": "MAI",
    "malayalam": "MAL",
    "manipuri": "MAN",
    "marathi": "MAR",
    "nepali": "NEP",
    "odia": "ODI",
    "punjabi": "PUN",
    "sanskrit": "SAN",
    "santali": "SANL",
    "sindhi": "SIN",
    "tamil": "TAM",
    "telugu": "TEL",
    "urdu": "URD"
}

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Database Connection ---
try:
    client = pymongo.MongoClient(DB_URL)
    db = client[DB_NAME]
    logger.info("Connected to MongoDB")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    sys.exit(1)

# --- Collections ---
users_collection = db["users"]
recordings_collection = db["recordings"]
logs_collection = db["logs"]
settings_collection = db["settings"]  # Collection for bot settings

# --- Database Index Setup ---
def setup_database_indexes():
    """Set up proper database indexes for the collections."""
    try:
        # Drop any existing problematic indexes
        try:
            recordings_collection.drop_index("user_id_1")
            logger.info("Dropped problematic user_id_1 index")
        except:
            pass
        
        # Create a unique index on recording_id
        recordings_collection.create_index("recording_id", unique=True, sparse=True)
        
        # Create a non-unique index on user_id for efficient queries
        recordings_collection.create_index("user_id")
        
        # Create indexes for users_collection
        users_collection.create_index("user_id", unique=True)
        
        # Create indexes for logs_collection
        logs_collection.create_index("user_id")
        logs_collection.create_index("timestamp")
        
        # Create indexes for settings_collection
        settings_collection.create_index("setting_key", unique=True)
        
        logger.info("Database indexes set up successfully")
    except Exception as e:
        logger.error(f"Error setting up database indexes: {e}")

# Setup indexes on startup
setup_database_indexes()

# --- Bot Settings ---
def get_bot_settings():
    """Get bot settings from database."""
    default_settings = {
        "max_file_size_mb": 4096,  # Default 4GB
        "custom_tag": "Madara2718",  # Default tag
        "upload_destination": "telegram",  # Default upload destination
        "max_duration_seconds": 14400,  # Default 4 hours in seconds
    }
    
    try:
        settings = {}
        db_settings = settings_collection.find({})
        for setting in db_settings:
            settings[setting["setting_key"]] = setting["setting_value"]
        
        # Merge with defaults, update DB if missing
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
                # Save default to database
                try:
                    settings_collection.insert_one({
                        "setting_key": key,
                        "setting_value": value
                    })
                except pymongo.errors.DuplicateKeyError:
                    pass # Ignore if already exists due to concurrent execution
        
        return settings
    except Exception as e:
        logger.error(f"Error getting bot settings: {e}")
        return default_settings

# Get initial settings
bot_settings = get_bot_settings()

def update_bot_setting(key, value):
    """Update a bot setting in the database."""
    try:
        settings_collection.update_one(
            {"setting_key": key},
            {"$set": {"setting_value": value}},
            upsert=True
        )
        bot_settings[key] = value
        return True
    except Exception as e:
        logger.error(f"Error updating bot setting {key}: {e}")
        return False

# Helper function to save bot settings (used for metadata reset)
def save_bot_settings():
    """Save current bot_settings dict to the database."""
    try:
        for key, value in bot_settings.items():
            settings_collection.update_one(
                {"setting_key": key},
                {"$set": {"setting_value": value}},
                upsert=True
            )
        logger.info("Bot settings saved to database.")
    except Exception as e:
        logger.error(f"Error saving bot settings: {e}")

# NEW: Database Channel Management Functions
def get_db_channel_info():
    """Get database channel information from MongoDB."""
    try:
        channel_info = settings_collection.find_one({"setting_key": "database_channel"})
        if channel_info:
            return channel_info.get("setting_value", {})
        return {
            "channel_id": None,  # Default to None until set
            "channel_name": "Not Set",
            "verified": False
        }
    except Exception as e:
        logger.error(f"Error getting database channel info: {e}")
        return {
            "channel_id": None,
            "channel_name": "Error",
            "verified": False
        }

def update_db_channel_info(channel_info):
    """Update database channel information in MongoDB."""
    try:
        settings_collection.update_one(
            {"setting_key": "database_channel"},
            {"$set": {"setting_value": channel_info}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating database channel info: {e}")
        return False

# --- Bot Setup ---
app = Client("m3u8_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Global State ---
class BotState:
    # MODIFIED: Added pending_duration_updates and progress tracking
    def __init__(self):
        self.active_recordings: Dict[int, dict] = {}  # user_id -> recording_info
        self.recording_processes: Dict[int, asyncio.subprocess.Process] = {}
        self.cleanup_tasks: Set[asyncio.Task] = set()
        self.maintenance_mode = False
        self.pending_tag_updates: Dict[int, int] = {}  # user_id -> message_id
        self.pending_duration_updates: Dict[int, int] = {}  # user_id -> message_id
        self.progress_trackers: Dict[int, asyncio.Task] = {}  # user_id -> progress tracking task
        
    def add_recording(self, user_id: int, recording_info: dict):
        self.active_recordings[user_id] = recording_info
        logger.info(f"Added recording for user {user_id}")
        
    def remove_recording(self, user_id: int):
        if user_id in self.active_recordings:
            logger.info(f"Removing recording for user {user_id}")
            del self.active_recordings[user_id]
        if user_id in self.recording_processes:
            del self.recording_processes[user_id]
        if user_id in self.progress_trackers:
            self.progress_trackers[user_id].cancel()
            del self.progress_trackers[user_id]
            
    def get_active_count(self) -> int:
        return len(self.active_recordings)
        
    def is_user_recording(self, user_id: int) -> bool:
        return user_id in self.active_recordings
    
    def get_active_recordings_details(self) -> List[dict]:
        """Get detailed information about all active recordings."""
        details = []
        for user_id, recording_info in self.active_recordings.items():
            details.append({
                "user_id": user_id,
                "filename": recording_info.get("filename", "Unknown"),
                "url": recording_info.get("url", ""),
                "start_time": recording_info.get("start_time"),
                "duration": recording_info.get("duration", 0)
            })
        return details

bot_state = BotState()

# --- Helper Functions ---
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    user = users_collection.find_one({"user_id": user_id})
    return user and user.get("is_admin", False)

def is_premium(user_id: int) -> bool:
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        return False
    
    premium_expiry = user.get("premium_expiry")
    if premium_expiry is None:  # Permanent premium
        return True
    
    # Handle datetime comparison properly
    current_time = get_ist_time()
    
    # Convert both to naive datetimes for comparison
    if isinstance(premium_expiry, datetime):
        if premium_expiry.tzinfo is not None:
            # Convert to naive datetime
            premium_expiry = premium_expiry.replace(tzinfo=None)
    
    return current_time < premium_expiry

def is_banned(user_id: int) -> bool:
    user = users_collection.find_one({"user_id": user_id})
    return user and user.get("is_banned", False)

def get_user_plan(user_id: int) -> str:
    if is_owner(user_id):
        return "Owner"
    elif is_admin(user_id):
        return "Admin"
    elif is_premium(user_id):
        return "Premium"
    else:
        return "Free"

def can_use_bot(user_id: int) -> bool:
    """Check if user is authorized to use the bot (owner, admin, or premium only)"""
    return is_owner(user_id) or is_admin(user_id) or is_premium(user_id)

def get_max_concurrent_recordings(user_id: int) -> int:
    """Get max concurrent recordings based on user plan"""
    if is_owner(user_id):
        return 999  # Unlimited for owner
    elif is_admin(user_id):
        return 5  # Admins can have 5 concurrent recordings
    elif is_premium(user_id):
        return 1  # Premium users can have 1 recording at a time
    else:
        return 0  # Free users can't record

def format_seconds(seconds):
    """Formats a duration in seconds into a HH:MM:SS string."""
    if seconds is None:
        return "N/A"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"

def format_bytes(bytes_size):
    """Format bytes to human readable format."""
    if bytes_size == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(bytes_size, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_size / p, 2)
    return f"{s} {size_names[i]}"

def to_dots(s: str) -> str:
    """Convert arbitrary string to dot.separated tokens (letters/digits only)."""
    if not s:
        return ""
    parts = re.findall(r"[A-Za-z0-9]+", s)
    return ".".join(p for p in parts if p)

def validate_m3u8_url(url: str) -> bool:
    """Validate if URL is a proper stream URL."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False

def detect_stream_type(url: str) -> str:
    """Detect if the stream is TS or M3U8 based on URL."""
    url_lower = url.lower()
    # Check for explicit TS extension
    if url_lower.endswith('.ts') or 'index.ts' in url_lower or '.ts?' in url_lower:
        return 'ts'
    # Check for M3U8 extension
    elif url_lower.endswith('.m3u8') or '.m3u8?' in url_lower:
        return 'm3u8'
    # Default to M3U8 for playlist-like URLs
    else:
        return 'm3u8'

def parse_duration(duration_str: str) -> Optional[int]:
    """Parse duration string and return total seconds."""
    try:
        duration_str = duration_str.strip()
        parts = duration_str.split(':')
        
        if len(parts) == 3:
            h, m, s = map(int, parts)
        elif len(parts) == 2:
            h = 0
            m, s = map(int, parts)
        elif len(parts) == 1:
            # Handle single number as seconds
            h = 0
            m = 0
            s = int(parts[0])
        else:
            return None
            
        if h < 0 or m < 0 or s < 0:
            return None
        if m >= 60 or s >= 60:
            return None
            
        total_seconds = h * 3600 + m * 60 + s
        return total_seconds if total_seconds > 0 else None
    except:
        return None

def sanitize_title(title: str) -> str:
    """Sanitize title for filename."""
    # Remove any extension if present
    title = os.path.splitext(title)[0]
    # Replace spaces and common separators with dots
    title = re.sub(r'[\s\-_]+', '.', title)
    # Remove invalid characters
    title = re.sub(r'[<>:"/\\|?*\[\]]', '', title)
    # Remove consecutive dots
    title = re.sub(r'\.+', '.', title)
    # Remove leading/trailing dots
    title = title.strip('.')
    # Limit length
    if len(title) > 100:
        title = title[:100].rstrip('.')
    return title or "Recording"

async def run_cmd(cmd, timeout=None):
    """Executes a shell command with timeout and better error handling."""
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        if timeout:
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except:
                    pass
                return "", "Command timed out", -1
        else:
            stdout, stderr = await process.communicate()
            
        return stdout.decode().strip(), stderr.decode().strip(), process.returncode
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return "", str(e), -1

async def check_url_accessibility(url: str) -> dict:
    """Check if URL is accessible and return status information."""
    try:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # Try a HEAD request first, fallback to GET
        curl_cmd = [
            "curl", "-s", "-I", "-m", "10",
            "-A", user_agent,
            "-H", "Accept: */*",
            url
        ]
        
        stdout, stderr, returncode = await run_cmd(curl_cmd, timeout=15)
        
        if returncode != 0:
            # Try GET with range request instead
            curl_cmd = [
                "curl", "-s", "-r", "0-1", "-m", "10",
                "-A", user_agent,
                "-o", "/dev/null", "-w", "%{http_code}",
                url
            ]
            stdout, _, returncode = await run_cmd(curl_cmd, timeout=15)
            
            if returncode == 0:
                try:
                    http_code = int(stdout)
                    if http_code >= 200 and http_code < 400:
                        return {"accessible": True, "http_code": http_code}
                except:
                    pass
            
            return {"accessible": False, "error": "Failed to reach URL"}
        
        # Parse headers to get HTTP code
        for line in stdout.split('\n'):
            if line.startswith('HTTP'):
                try:
                    http_code = int(line.split()[1])
                    if http_code >= 200 and http_code < 400:
                        return {"accessible": True, "http_code": http_code}
                    else:
                        return {"accessible": False, "http_code": http_code, "error": f"HTTP {http_code}"}
                except:
                    pass
        
        return {"accessible": True, "http_code": 200}
        
    except Exception as e:
        logger.error(f"URL check error: {e}")
        return {"accessible": True, "http_code": 200, "warning": "Check failed but allowing"}

async def get_stream_info(url: str) -> dict:
    """Get detailed stream information with quality and language detection."""
    stream_type = detect_stream_type(url)
    
    info = {
        'stream_name': 'LiveStream',
        'video_quality': '720',
        'video_codec': 'H264',
        'audio_present': True,
        'audio_formats': ['AAC'],
        'audio_languages': ['UND'],
        'audio_languages_ordered': ['UND'],  # Add this to preserve order
        'audio_channels': '2.0',
        'duration': None,
        'bitrate': None,
        'stream_type': stream_type,
        'error': None
    }
    
    try:
        # Extract stream name from URL
        parsed_url = urlparse(url)
        path_segments = [seg for seg in parsed_url.path.split('/') if seg]
        if path_segments:
            last_segment = path_segments[-1]
            stream_name = last_segment.rsplit('.', 1)[0] if '.' in last_segment else last_segment
            info['stream_name'] = stream_name
        
        # Build ffprobe command with aggressive error suppression for all stream types
        ffprobe_cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-read_intervals", "%+0.1",
            url
        ]
        
        stdout, stderr, returncode = await run_cmd(ffprobe_cmd, timeout=30)
        
        if returncode == 0 and stdout:
            try:
                data = json.loads(stdout)
                streams = data.get("streams", [])
                format_info = data.get("format", {})

                # Analyze video streams for quality
                for stream in streams:
                    if stream.get("codec_type") == "video":
                        height = stream.get("height")
                        if height:
                            # Improved quality detection with more precise ranges
                            if height >= 2160:
                                info['video_quality'] = '4K'
                            elif height >= 1440:
                                info['video_quality'] = '1440'
                            elif height >= 1080:
                                info['video_quality'] = '1080'
                            elif height >= 720:
                                info['video_quality'] = '720'
                            elif height >= 576:  # Add 576p detection
                                info['video_quality'] = '576'
                            elif height >= 480:
                                info['video_quality'] = '480'
                            else:
                                info['video_quality'] = '360'
                        
                        codec = stream.get("codec_name", "h264").upper()
                        if codec == "H264":
                            info['video_codec'] = "H264"
                        elif codec == "H265" or codec == "HEVC":
                            info['video_codec'] = "H265"
                        else:
                            info['video_codec'] = codec

                # Analyze audio streams for languages and formats - PRESERVE ORDER
                audio_languages = []
                audio_languages_ordered = []  # Maintain original order
                audio_formats = []
                
                for stream in streams:
                    if stream.get("codec_type") == "audio":
                        info['audio_present'] = True
                        
                        # Get audio codec
                        codec_name = stream.get("codec_name", "aac").upper()
                        if codec_name == "AAC":
                            audio_format = "AAC"
                        elif codec_name == "AC3":
                            audio_format = "AC3"
                        elif codec_name == "EAC3":
                            audio_format = "EAC3"
                        elif codec_name == "MP2":
                            audio_format = "MP2"  # Add MP2 support
                        elif codec_name == "MP3":
                            audio_format = "MP3"
                        else:
                            audio_format = codec_name
                        
                        audio_formats.append(audio_format)
                        
                        # Get audio language
                        tags = stream.get("tags", {})
                        language = tags.get("language", "und").lower()
                        
                        if language in LANGUAGE_MAPPING:
                            lang_code = LANGUAGE_MAPPING[language]
                        elif language != "und":
                            lang_code = language.upper()
                        else:
                            lang_code = "UND"
                        
                        # Add to ordered list (preserve stream order)
                        audio_languages_ordered.append(lang_code)
                        
                        # Get audio channels with consistent formatting
                        channels = stream.get("channels", 2)
                        if channels == 1:
                            channels_str = "1.0"
                        elif channels == 2:
                            channels_str = "2.0"
                        elif channels == 6:
                            channels_str = "5.1"
                        elif channels == 8:
                            channels_str = "7.1"
                        else:
                            channels_str = f"{channels}.0"
                        
                        info['audio_channels'] = channels_str
                
                # Set audio languages (ordered) and formats
                info['audio_languages'] = list(dict.fromkeys(audio_languages_ordered))  # Remove duplicates but preserve order
                info['audio_languages_ordered'] = audio_languages_ordered  # Keep original order
                info['audio_formats'] = list(set(audio_formats)) if audio_formats else ['AAC']
                
                # Get format info
                if 'duration' in format_info:
                    try:
                        info['duration'] = float(format_info['duration'])
                    except:
                        pass
                if 'bit_rate' in format_info:
                    try:
                        info['bitrate'] = int(format_info['bit_rate'])
                    except:
                        pass
                    
            except json.JSONDecodeError:
                pass
        
    except Exception as e:
        logger.warning(f"Stream info extraction warning: {e}")
    
    return info

def generate_filename(title: str, start_time: datetime, duration_seconds: int, 
                     quality: str, audio_languages: List[str], 
                     audio_format: str, audio_channels: str, 
                     video_codec: str, stream_type: str = 'm3u8') -> str:
    """Generate filename in the specified format using IST - .mkv for TS streams, .mkv for M3U8."""
    # Convert to IST
    ist_time = start_time
    date_str = ist_time.strftime("%d-%m-%Y")
    end_time = ist_time + timedelta(seconds=duration_seconds)
    time_range = f"{ist_time.strftime('%H.%M')}-{end_time.strftime('%H.%M')}"
    
    # Clean metadata components
    quality = str(quality).replace('p', '').replace('Quality', '').replace('4K', '4K').strip() or "720"
    audio_format = str(audio_format).replace('Audio', '').strip() or "AAC"
    
    # Fix audio channels formatting - ensure consistent decimal format
    audio_channels = str(audio_channels).replace('.0', '').strip()
    if audio_channels.isdigit():  # If it's just a number like "2", make it "2.0"
        audio_channels = f"{audio_channels}.0"
    audio_channels = audio_channels or "2.0"
    
    video_codec = str(video_codec).replace('Codec', '').strip() or "H264"
    
    # Join audio languages in the order they appear in the stream
    # Use audio_languages (which should be ordered) instead of creating a set
    audio_str = "-".join([str(lang).strip() for lang in audio_languages if lang and str(lang).strip()]) if audio_languages else "UND"
    
    # Sanitize title
    title = sanitize_title(title)
    
    # Get custom tag from settings
    custom_tag = bot_settings.get("custom_tag", "Madara2718")
    
    # Always use .mkv extension regardless of stream type
    extension = '.mkv'
    
    filename = (
        f"{title}.[{date_str}].[{time_range}].{quality}p.TV-DL."
        f"{audio_str}.{audio_format}.{audio_channels}.{video_codec}-{custom_tag}{extension}"
    )
    
    return filename

async def shorten_url(long_url: str) -> str:
    """Shorten URL using shortlink API."""
    if not SHORTLINK_API_TOKEN:
        return long_url
    
    try:
        # This is a placeholder for a real shortlink API
        # Replace with actual API implementation
        return long_url
    except Exception as e:
        logger.error(f"Failed to shorten URL: {e}")
        return long_url

async def cleanup_files(*files):
    """Clean up files safely."""
    for file in files:
        try:
            if file and os.path.exists(file):
                os.remove(file)
                logger.info(f"Cleaned up file: {file}")
        except Exception as e:
            logger.error(f"Failed to cleanup {file}: {e}")

async def log_activity(user_id: int, action: str, details: dict = None):
    """Log user activity."""
    try:
        log_entry = {
            "user_id": user_id,
            "action": action,
            "timestamp": get_ist_time(),
            "details": details or {}
        }
        logs_collection.insert_one(log_entry)
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

async def get_actual_video_duration(file_path: str) -> int:
    """Get the actual duration of a video file using ffprobe."""
    try:
        cmd = [FFPROBE_PATH, "-v", "error", "-show_format", "-print_format", "json", file_path]
        stdout, _, returncode = await run_cmd(cmd)
        
        if returncode == 0 and stdout:
            try:
                data = json.loads(stdout)
                duration = float(data.get("format", {}).get("duration", 0))
                return int(duration)
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Fallback to ffmpeg method
        cmd = [FFMPEG_PATH, "-i", file_path, "-f", "null", "-"]
        _, stderr, _ = await run_cmd(cmd)
        
        # Parse duration from stderr
        duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", stderr)
        if duration_match:
            h, m, s = map(float, duration_match.groups())
            return int(h * 3600 + m * 60 + s)
        
        return 0
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")
        return 0

async def update_file_metadata(file_path: str, title: str, start_time: datetime, actual_duration: int):
    """Update file metadata with correct duration and creation time."""
    try:
        temp_file = file_path + ".temp.mkv"
        
        # Create metadata tags
        metadata_tags = [
            "-metadata", f"title={title}",
            "-metadata", f"encoder=M3U8 Recorder Bot by {bot_settings.get('custom_tag', 'Madara2718')}",
            "-metadata", f"creation_time={start_time.isoformat()}"
        ]
        
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", file_path,
            "-c", "copy",
            "-map", "0"
        ]
        
        # Add main metadata
        cmd.extend(metadata_tags)
        
        cmd.append(temp_file)
        
        _, _, returncode = await run_cmd(cmd)
        
        if returncode == 0 and os.path.exists(temp_file):
            # Replace original with temp file
            os.replace(temp_file, file_path)
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error updating file metadata: {e}")
        return False

async def rename_file_with_actual_duration(file_path: str, title: str, start_time: datetime, 
                                         actual_duration: int, quality: str, audio_languages: List[str], 
                                         audio_format: str, audio_channels: str, 
                                         video_codec: str, stream_type: str = 'm3u8') -> str:
    """Rename file with actual duration in filename."""
    try:
        # Generate new filename with actual duration
        new_filename = generate_filename(
            title=title,
            start_time=start_time,
            duration_seconds=actual_duration,
            quality=quality,
            audio_languages=audio_languages,
            audio_format=audio_format,
            audio_channels=audio_channels,
            video_codec=video_codec,
            stream_type=stream_type
        )
        
        # Create new file path
        new_file_path = os.path.join(os.path.dirname(file_path), new_filename)
        
        # Rename the file
        os.rename(file_path, new_file_path)
        
        return new_file_path
    except Exception as e:
        logger.error(f"Error renaming file: {e}")
        return file_path

# NEW: Function to upload file to Gofile
async def upload_to_gofile(file_path: str, status_msg=None, filename: str = "") -> dict:
    """Upload file to Gofile and return download link with progress tracking."""
    try:
        import aiohttp
        
        file_size = os.path.getsize(file_path)
        
        actual_filename = filename or os.path.basename(file_path)
        
        # Get the best server first
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.gofile.io/servers') as resp:
                    if resp.status == 200:
                        servers_data = await resp.json()
                        if servers_data.get("status") == "ok" and servers_data.get("data", {}).get("servers"):
                            # Get the first available server
                            servers = servers_data["data"]["servers"]
                            if servers:
                                server = servers[0]["name"]
                                upload_url = f"https://{server}.gofile.io/contents/uploadfile"
                            else:
                                upload_url = "https://store1.gofile.io/contents/uploadfile"
                        else:
                            upload_url = "https://store1.gofile.io/contents/uploadfile"
                    else:
                        upload_url = "https://store1.gofile.io/contents/uploadfile"
        except Exception as e:
            logger.warning(f"Failed to get GoFile server: {e}, defaulting to store1")
            upload_url = "https://store1.gofile.io/contents/uploadfile"
        
        # Update status if available
        if status_msg:
            try:
                await status_msg.edit(
                    f"⬆️ **Uploading to GoFile**\n\n"
                    f"📁 **File:** `{actual_filename}`\n"
                    f"📊 **Size:** `{format_bytes(file_size)}`\n"
                    f"🔄 **Uploading... Please wait**"
                )
            except Exception as e:
                logger.warning(f"Failed to edit status message for GoFile upload: {e}")
        
        # Upload the file
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=actual_filename)
                
                async with session.post(upload_url, data=data) as resp:
                    if resp.status != 200:
                        return {"success": False, "error": f"Upload failed: HTTP {resp.status}"}
                    
                    upload_data = await resp.json()
                    
                    if upload_data.get("status") != "ok":
                        return {"success": False, "error": f"Upload error: {upload_data.get('status', 'Unknown')}"}
                    
                    # Extract file information
                    data_obj = upload_data.get("data", {})
                    download_page = data_obj.get("downloadPage", "")
                    
                    if not download_page:
                        return {"success": False, "error": "No download link received"}
                    
                    return {
                        "success": True,
                        "download_link": download_page,
                        "file_id": data_obj.get("fileId", ""),
                        "file_name": actual_filename
                    }
    
    except Exception as e:
        logger.error(f"Error uploading to Gofile: {e}")
        return {"success": False, "error": str(e)}

# NEW: Bot initialization and channel access functions
async def ensure_bot_ready(client, max_retries=5, delay=2):
    """Ensure bot is fully ready to perform operations."""
    for attempt in range(max_retries):
        try:
            # Try to get bot info to verify connection
            await client.get_me()
            return True
        except Exception as e:
            logger.warning(f"Bot not ready (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
    return False

async def safe_forward_to_channel(client, message, channel_id, max_retries=3):
    """Safely forward message with retries."""
    for attempt in range(max_retries):
        try:
            # Ensure bot is ready
            if not await ensure_bot_ready(client):
                logger.error("Bot not ready after retries, skipping forward")
                return False
            
            # Try to forward the message
            await message.copy(chat_id=channel_id)
            logger.info(f"Successfully forwarded to channel {channel_id}")
            return True
        except Exception as e:
            logger.warning(f"Forward attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed to forward after {max_retries} attempts: {e}")
                return False
    return False

async def safe_send_to_channel(client, text, channel_id, max_retries=3):
    """Safely send message to channel with retries."""
    for attempt in range(max_retries):
        try:
            # Ensure bot is ready
            if not await ensure_bot_ready(client):
                logger.error("Bot not ready after retries, skipping send")
                return False
            
            # Try to send the message
            await client.send_message(
                chat_id=channel_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            )
            logger.info(f"Successfully sent to channel {channel_id}")
            return True
        except Exception as e:
            logger.warning(f"Send attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed to send after {max_retries} attempts: {e}")
                return False
    return False

async def forward_to_database_channel(client: Client, message: Message, duration: int = 0):
    """Forward uploaded content to database channel without forward tag."""
    try:
        # Get database channel info from MongoDB
        db_channel_info = get_db_channel_info()
        channel_id = db_channel_info.get("channel_id")
        
        # Skip if no channel is set
        if not channel_id:
            logger.warning("No database channel configured. Skipping forward.")
            return
        
        # Skip if duration is 1 minute or less
        if duration > 0 and duration <= 60:
            logger.info(f"Skipping database forward - duration {duration}s is ≤ 60s")
            return
        
        # Use safe forward with retries
        await safe_forward_to_channel(client, message, channel_id)
        
    except Exception as e:
        logger.error(f"Error in forward_to_database_channel: {e}")

async def send_gofile_to_database_channel(client: Client, user_chat_id: int, filename: str, download_link: str, file_size: int, duration: int):
    """Send GoFile link message to database channel."""
    try:
        # Get database channel info from MongoDB
        db_channel_info = get_db_channel_info()
        channel_id = db_channel_info.get("channel_id")
        
        # Skip if no channel is set
        if not channel_id:
            logger.warning("No database channel configured. Skipping send.")
            return
        
        # Skip if duration is 1 minute or less
        if duration > 0 and duration <= 60:
            logger.info(f"Skipping database forward - duration {duration}s is ≤ 60s")
            return
        
        caption = (
            f"<b>📹 {filename}</b>\n\n"
            f"💾 Size: {format_bytes(file_size)}\n"
            f"⏱️ Duration: {format_seconds(duration)}\n\n"
            f"🔗 <a href='{download_link}'>Download from GoFile</a>"
        )
        
        # Use safe send with retries
        await safe_send_to_channel(client, caption, channel_id)
        
    except Exception as e:
        logger.error(f"Error in send_gofile_to_database_channel: {e}")

# NEW: Helper function to display the main settings menu
async def show_main_settings(client, message):
    """Show the main settings menu."""
    # Get current settings
    custom_tag = bot_settings.get("custom_tag", "Madara2718")
    upload_destination = bot_settings.get("upload_destination", "telegram")
    max_duration_seconds = bot_settings.get("max_duration_seconds", 14400)
    
    # Get database channel info
    db_channel_info = get_db_channel_info()
    channel_id = db_channel_info.get("channel_id")
    channel_name = db_channel_info.get("channel_name", "Not Set")
    verified = db_channel_info.get("verified", False)
    
    # Format duration display
    hours = max_duration_seconds // 3600
    minutes = (max_duration_seconds % 3600) // 60
    seconds = max_duration_seconds % 60
    duration_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    # Format upload destination display
    upload_display = "Telegram (as media)" if upload_destination == "telegram" else "Gofile (link)"
    
    # Format database channel display
    channel_status = "✅ Verified" if verified else "❌ Not verified"
    
    settings_text = (
        f"⚙️ **Bot Settings**\n\n"
        f"🏷️ **Custom Tag:** `{custom_tag}`\n"
        f"☁️ **Upload Destination:** `{upload_display}`\n"
        f"⏱️ **Max Duration:** `{duration_display}`\n\n"
        f"📢 **Database Channel:**\n"
        f"• ID: `{channel_id}`\n"
        f"• Name: {channel_name}\n"
        f"• Status: {channel_status}\n\n"
        f"ℹ️ **Note:** Files larger than 1.95GB will be automatically uploaded to GoFile regardless of upload destination setting."
    )
    
    try:
        await message.edit(
            text=settings_text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🏷️ Custom Tag", callback_data="settings_tag"),
                    InlineKeyboardButton("☁️ Upload Destination", callback_data="settings_upload_destination")
                ],
                [
                    InlineKeyboardButton("⏱️ Max Duration", callback_data="settings_max_duration"),
                    InlineKeyboardButton("📢 Database Channel", callback_data="settings_dbchannel")
                ],
                [
                    InlineKeyboardButton("🔒 Close", callback_data="close")
                ]
            ])
        )
    except MessageNotModified:
        pass # Ignore if the message content hasn't changed

# --- Middleware for Authorization Check ---
async def check_authorization(client, message):
    """Check if user is authorized to use the bot."""
    # Handle both regular messages and callback queries
    if hasattr(message, 'from_user'):
        user_id = message.from_user.id
        is_callback = False
    else:
        # For callback queries
        user_id = message.message.from_user.id
        is_callback = True
    
    # Check if user is banned
    if is_banned(user_id):
        if is_callback:
            await message.answer("You are banned from using this bot.", show_alert=True)
        else:
            await message.reply(
                "🚫 **Access Denied**\n\n"
                "You are banned from using this bot. Please contact @II_Madara_II to resolve issue.",
                disable_web_page_preview=True,
                reply_to_message_id=message.id
            )
        return False
    
    # Check if bot is in maintenance mode
    if bot_state.maintenance_mode and not is_owner(user_id):
        if is_callback:
            await message.answer("Bot is under maintenance.", show_alert=True)
        else:
            await message.reply(
                "🔧 **Bot Under Maintenance**\n\n"
                "The Bot is currently in Maintenance Mode.\n\n"
                "Please try again later. For updates, contact @II_Madara_II",
                disable_web_page_preview=True,
                reply_to_message_id=message.id
            )
        return False
    
    return True

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """Handles the /start command."""
    user_id = message.from_user.id
    user = users_collection.find_one({"user_id": user_id})
    
    if not user:
        # Create new user entry
        users_collection.insert_one({
            "user_id": user_id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "plan": "Free",
            "created_at": get_ist_time(),
            "premium_expiry": None,
            "is_admin": False,
            "is_banned": False
        })
        user = {"plan": "Free"}
    
    plan = get_user_plan(user_id)
    
    # Updated bot style welcome message
    await message.reply(
        f"Hello {message.from_user.mention}\n\n"
        "🤖 I'm an M3U8 Recorder Bot.\n"
        "🎥 Record any live stream URL (M3U8) directly with ease.\n\n"
        "🔐 Subscription is required to use this bot.\n\n"
        "📖 Use /help to learn how to use the bot.\n"
        "💳 Check /subscription to subscribe and get access.",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("👨‍💻 About", callback_data="about"),
                InlineKeyboardButton("🔒 Close", callback_data="close")
            ]]
        ),
        reply_to_message_id=message.id
    )
    
    await log_activity(user_id, "start", {"plan": plan})

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    """Handles the /help command."""
    user_id = message.from_user.id
    plan = get_user_plan(user_id)
    
    help_text = (
        "📖 **M3U8 Recording Bot Help**\n\n"
        "**Basic Commands:**\n"
        "• /record [link] [duration] [title] - Record a stream\n"
        "• /cancel - Cancel your active recording\n"
        "• /myplan - Check your current plan and limits\n\n"
        "**Examples:**\n"
        "• /record https://example.com/stream.m3u8 01:30:00 My Show\n"
        "• /record https://example.com/index.ts?id=a02p 00:45:00 Episode 1\n\n"
    )
    
    if plan == "Premium":
        help_text += (
            "**Premium Features:**\n"
            "• 1 concurrent recording at a time\n"
            "• Extended recording duration\n"
            "• Priority processing\n\n"
        )
    
    help_text += (
        "**Recording Format:**\n"
        "• Duration format: HH:MM:SS (e.g., 01:30:00)\n"
        "• Supported formats: M3U8 streams (.m3u8) and TS streams (.ts)\n"
        "• Output format: .mkv\n\n"
        "**File Naming:**\n"
        "Files are named in format:\n"
        "[title].[date].[time-range].[quality].TV-DL.[languages].[format].[channels].[codec]-[tag].mkv\n\n"
        "For support, contact @II_Madara_II"
    )
    
    await message.reply(help_text, disable_web_page_preview=True, reply_to_message_id=message.id)
    await log_activity(user_id, "help")

@app.on_message(filters.command("subscription") & filters.private)
async def subscription_command(client, message):
    """Handles the /subscription command to show subscription plans."""
    user_id = message.from_user.id
    
    # Create subscription plan text
    subscription_text = (
        "💎 **Premium Subscription Plans**\n\n"
        "🔹 **1 Day** - ₹10\n"
        "🔹 **1 Month** - ₹79\n"
        "🔹 **3 Months** - ₹199\n"
        "🔹 **6 Months** - ₹349\n"
        "🔹 **12 Months** - ₹599\n\n"
        "💳 **Payment Method:** UPI Only\n\n"
        "📱 **UPI ID:** `9641034873@ybl`\n\n"
        "📸 **QR Code:** [Click to view](https://iili.io/fg6uV0F.jpg)\n\n"
        "🔐 **How to Subscribe:**\n"
        "1️⃣ Choose a plan from the list above\n"
        "2️⃣ Send payment to the UPI ID or scan the QR code\n"
        "3️⃣ Send screenshot of payment to @II_Madara_II\n"
        "4️⃣ Mention your plan number and user ID in the message\n\n"
        "🆔 **Your User ID:** `" + str(user_id) + "`\n\n"
        "⏳ After payment verification, your premium access will be activated within 24 hours.\n\n"
        "❓ For any queries, contact @II_Madara_II"
    )
    
    await message.reply(
        subscription_text,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📸 View QR Code", url="https://iili.io/fg6uV0F.jpg"),
                    InlineKeyboardButton("💬 Contact Support", url="https://t.me/II_Madara_II")
                ]
            ]
        ),
        reply_to_message_id=message.id
    )
    
    await log_activity(user_id, "subscription_view")

@app.on_message(filters.command("record") & filters.private)
async def record_command(client, message):
    """Handles the /record command."""
    user_id = message.from_user.id
    
    # Check if user is authorized to use the bot
    if not can_use_bot(user_id):
        await message.reply(
            "🔒 **Subscription Required**\n\n"
            "❌ You need an active subscription to use this feature.\n\n"
            "Use /subscription to view available plans and payment options.",
            reply_to_message_id=message.id
        )
        return
    
    # Check if user has reached their concurrent recording limit
    max_recordings = get_max_concurrent_recordings(user_id)
    current_recordings = sum(1 for uid in bot_state.active_recordings if uid == user_id)
    
    if current_recordings >= max_recordings:
        limit_text = "unlimited" if max_recordings >= 999 else str(max_recordings)
        await message.reply(f"❌ You've reached your limit of {limit_text} concurrent recordings. Use /cancel to stop an active recording.", reply_to_message_id=message.id)
        return
    
    # Parse command arguments
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.reply(
            "❌ Invalid command format.\n\n"
            "Usage: /record [link] [duration] [title]\n\n"
            "Example: /record https://example.com/stream.m3u8 01:30:00 My Show",
            reply_to_message_id=message.id
        )
        return
    
    url = parts[1]
    duration_str = parts[2]
    title = parts[3]
    
    # Validate URL
    if not validate_m3u8_url(url):
        await message.reply("❌ Invalid URL. Please provide a valid stream link.", reply_to_message_id=message.id)
        return
    
    # Validate duration
    duration_seconds = parse_duration(duration_str)
    if not duration_seconds:
        await message.reply("❌ Invalid duration format. Please use HH:MM:SS format (e.g., 01:30:00).", reply_to_message_id=message.id)
        return
    
    # Check against max duration setting
    max_duration = bot_settings.get("max_duration_seconds", 14400)  # Default 4 hours
    if duration_seconds > max_duration:
        max_duration_str = format_seconds(max_duration)
        await message.reply(
            f"❌ Duration exceeds the maximum allowed limit.\n\n"
            f"Requested: {duration_str}\n"
            f"Maximum allowed: {max_duration_str}\n\n"
            f"Please use a shorter duration.",
            reply_to_message_id=message.id
        )
        return
    
    # Start recording
    await start_recording(client, message, url, duration_seconds, title)

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client, message):
    """Handles the /cancel command to stop active recording."""
    user_id = message.from_user.id
    
    # Check if user is authorized to use the bot
    if not can_use_bot(user_id):
        await message.reply(
            "🔒 **Subscription Required**\n\n"
            "❌ You need an active subscription to use this feature.\n\n"
            "Use /subscription to view available plans and payment options.",
            reply_to_message_id=message.id
        )
        return
    
    # Check if user has active recording
    if not bot_state.is_user_recording(user_id):
        await message.reply("❌ You don't have any active recording to cancel.", reply_to_message_id=message.id)
        return
    
    try:
        # Get recording info before killing the process
        recording_info = bot_state.active_recordings.get(user_id)
        if not recording_info:
            await message.reply("❌ Recording information not found.", reply_to_message_id=message.id)
            return
        
        output_file = recording_info.get('filename')
        thumbnail_file = recording_info.get('thumbnail')
        chat_id = recording_info.get('chat_id')
        status_msg_id = recording_info.get('status_msg_id')
        recording_id = recording_info.get('recording_id')
        title = recording_info.get('title', 'Recording')
        start_time = recording_info.get('start_time', get_ist_time())
        quality = recording_info.get('quality', '720')
        audio_languages = recording_info.get('audio_languages', ['UND'])
        audio_format = recording_info.get('audio_format', 'AAC')
        audio_channels = recording_info.get('audio_channels', '2.0')
        video_codec = recording_info.get('video_codec', 'H264')
        stream_type = recording_info.get('stream_type', 'm3u8')
        original_duration = recording_info.get('duration', 0)
        
        # Kill the FFmpeg process
        if user_id in bot_state.recording_processes:
            process = bot_state.recording_processes[user_id]
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
        
        # Update status message
        try:
            await client.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text="🚫 **Recording Cancelled**\n\nProcessing the partially recorded file..."
            )
        except MessageNotModified:
            pass
        except Exception as e:
            logger.warning(f"Could not edit status message for cancel: {e}")
        
        # Get actual duration of the recorded file
        actual_duration = 0
        if output_file and os.path.exists(output_file):
            actual_duration = await get_actual_video_duration(output_file)
            
            # Update metadata with correct duration
            await update_file_metadata(output_file, title, start_time, actual_duration)
            
            # Rename file with actual duration
            output_file = await rename_file_with_actual_duration(
                output_file, title, start_time, actual_duration,
                quality, audio_languages, audio_format, video_codec, stream_type
            )
            
            # Update recording info with new filename
            recording_info['filename'] = output_file
            recording_info['actual_duration'] = actual_duration
        
        # Update status message
        try:
            await client.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"🚫 **Recording Cancelled**\n\nActual duration: {format_seconds(actual_duration)}\n\nProcessing file for upload..."
            )
        except MessageNotModified:
            pass
        except Exception as e:
            logger.warning(f"Could not edit status message after duration update: {e}")
        
        # Remove from active recordings
        bot_state.remove_recording(user_id)
        
        # Update database
        if recording_id:
            recordings_collection.update_one(
                {"recording_id": recording_id},
                {"$set": {"status": "cancelled", "cancelled_at": get_ist_time(), "actual_duration": actual_duration}}
            )
        
        # Process the partially recorded file if it exists and has content
        if output_file and os.path.exists(output_file) and os.path.getsize(output_file) > 1000:  # At least 1KB
            # Get the filename without path for display
            filename = os.path.basename(output_file)
            
            # Process the cancelled recording
            await process_completed_recording(
                client, message, 
                await client.get_messages(chat_id, status_msg_id), 
                output_file, thumbnail_file, filename, 
                user_id, recording_id, cancelled=True
            )
        else:
            # Delete the status message after a short delay
            await asyncio.sleep(3)
            try:
                await client.delete_messages(chat_id=chat_id, message_ids=status_msg_id)
            except:
                pass
            
            # Cleanup files
            await cleanup_files(output_file, thumbnail_file)
        
        await log_activity(message.from_user.id, "cancel_recording", {"actual_duration": actual_duration})
        
    except Exception as e:
        logger.error(f"Error cancelling recording: {e}", exc_info=True)
        await message.reply(f"❌ Error while cancelling: {str(e)[:200]}", reply_to_message_id=message.id)

@app.on_message(filters.command("myplan") & filters.private)
async def myplan_command(client, message):
    """Handles the /myplan command."""
    user_id = message.from_user.id
    user = users_collection.find_one({"user_id": user_id})
    
    if not user:
        await message.reply("❌ User not found in database.", reply_to_message_id=message.id)
        return
    
    plan = get_user_plan(user_id)
    premium_expiry = user.get("premium_expiry")
    
    # Create plan display with emojis
    plan_emoji = {
        "Owner": "👑",
        "Admin": "🛡️",
        "Premium": "💎",
        "Free": "🆓"
    }
    
    # Function to update the message with current time
    async def update_plan_message():
        # Get current time for fresh calculation
        current_time = get_ist_time()
        
        # Calculate expiry text if premium
        if plan == "Premium" and premium_expiry is not None:
            if isinstance(premium_expiry, datetime) and premium_expiry.tzinfo is not None:
                premium_expiry_naive = premium_expiry.replace(tzinfo=None)
            else:
                premium_expiry_naive = premium_expiry
            
            if premium_expiry_naive > current_time:
                # Calculate time left in hours, minutes, and seconds
                time_left = premium_expiry_naive - current_time
                days = time_left.days
                hours, remainder = divmod(time_left.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                if days > 0:
                    expiry_text = f"{days} days, {hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    expiry_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                expiry_text = "Expired - Please renew"
        elif plan == "Premium" and premium_expiry is None:
            expiry_text = "Permanent"
        else:
            expiry_text = ""
        
        # Get max duration from settings and format it
        max_duration_seconds = bot_settings.get("max_duration_seconds", 14400)
        max_duration_str = format_seconds(max_duration_seconds)
        
        # Build the plan text with clean professional format
        plan_text = (
            f"{plan_emoji.get(plan, '📊')} **Subscription Overview**\n\n"
            f"👤 **User:** {message.from_user.mention}\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"📦 **Current Plan:** **{plan}**\n\n"
        )
        
        if plan == "Premium":
            plan_text += (
                f"⏳ **Plan Validity:** {expiry_text}\n\n"
                f"💎 **Premium Features**\n\n"
                f"• ♾️ Unlimited M3U8 recordings\n"
                f"• 🎥 1 recording at a time\n"
                f"• ⚡ No queue – instant start\n"
                f"• 🕒 Max Duration: {max_duration_str}\n"
                f"• 🚀 Stable & fast processing\n"
                f"• 🔓 Full access to all recorder features\n\n"
            )
        
        elif plan == "Free":
            plan_text += (
                f"🔒 **Subscription Status:** Inactive\n\n"
                f"✨ **What You Get with Premium**\n\n"
                f"• ♾️ Unlimited M3U8 recordings\n"
                f"• 🎥 1 recording at a time\n"
                f"• ⚡ No queue – instant start\n"
                f"• 🕒 Extended recording duration\n"
                f"• 🚀 Stable & fast processing\n"
                f"• 🔓 Access to all features\n\n"
                f"💳 **Upgrade Now**\n"
                f"Use /subscription to view plans & payment options.\n\n"
            )
        
        else:  # Owner / Admin
            plan_text += (
                f"⚡ **Special Access: Owner / Admin**\n\n"
                f"🛠 **Admin Features**\n\n"
                f"• ♾️ Unlimited M3U8 recordings\n"
                f"• 🔁 Unlimited concurrent recordings\n"
                f"• ⚡ No queue – instant start\n"
                f"• 🕒 Max Duration: {max_duration_str}\n"
                f"• 🚀 Ultra-fast & stable processing\n"
                f"• 🧩 Full admin command access\n\n"
            )
        
        plan_text += (
            f"📞 **Support:** @II_Madara_II"
        )
        
        return plan_text
    
    # Send initial message
    plan_text = await update_plan_message()
    sent_message = await message.reply(plan_text, disable_web_page_preview=True, reply_to_message_id=message.id)
    
    # Start auto-update task if premium and has expiry
    if plan == "Premium" and premium_expiry is not None:
        # Create a task to update the message every second
        async def update_task():
            try:
                # Update for up to 60 seconds or until message is deleted
                for _ in range(60):
                    await asyncio.sleep(1)
                    try:
                        # Get updated text
                        updated_text = await update_plan_message()
                        # Edit the message
                        await sent_message.edit_text(updated_text, disable_web_page_preview=True)
                    except MessageNotModified:
                        # Message content hasn't changed, continue
                        continue
                    except Exception as e:
                        # If message was deleted or other error, stop updating
                        logger.warning(f"Error updating plan message: {e}")
                        break
            except Exception as e:
                logger.error(f"Error in plan update task: {e}")
        
        # Start the update task
        asyncio.create_task(update_task())
    
    await log_activity(user_id, "myplan", {"plan": plan})

@app.on_message(filters.command("settings") & filters.private)
async def settings_command(client, message):
    """Handles the /settings command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    # Call the helper function to display settings
    reply_message = await message.reply("⚙️ Loading settings...", reply_to_message_id=message.id)
    await show_main_settings(client, reply_message)
    
    await log_activity(user_id, "settings")

@app.on_message(filters.command("setdbchannel") & filters.private)
async def setdbchannel_command(client, message):
    """Handles the /setdbchannel command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    # Check if message contains a channel ID or is a forward from a channel
    if message.forward_from_chat:
        # Message is forwarded from a channel
        channel_id = message.forward_from_chat.id
        channel_name = message.forward_from_chat.title
    elif message.text and len(message.text.split()) > 1:
        # Command contains channel ID
        try:
            channel_id = int(message.text.split()[1])
            channel_name = "Unknown Channel"
        except ValueError:
            await message.reply("❌ Invalid channel ID format. Please provide a valid channel ID.", reply_to_message_id=message.id)
            return
    else:
        await message.reply(
            "❌ Please provide a channel ID or forward a message from the channel.\n\n"
            "Usage: /setdbchannel [channel_id]\n"
            "Or forward a message from the channel and use /setdbchannel",
            reply_to_message_id=message.id
        )
        return
    
    # Verify the channel
    try:
        chat = await client.get_chat(channel_id)
        
        # Update channel info in MongoDB
        channel_info = {
            "channel_id": channel_id,
            "channel_name": chat.title,
            "verified": True,
            "last_verified": get_ist_time().isoformat()
        }
        update_db_channel_info(channel_info)
        
        await message.reply(
            f"✅ **Database Channel Updated**\n\n"
            f"📢 **Channel:** {chat.title}\n"
            f"🆔 **ID:** `{channel_id}`\n\n"
            f"The bot will now use this channel for database operations.",
            reply_to_message_id=message.id
        )
        
        await log_activity(user_id, "setdbchannel", {
            "channel_id": channel_id,
            "channel_name": chat.title
        })
        
    except Exception as e:
        logger.error(f"Error verifying channel: {e}")
        await message.reply(
            f"❌ **Failed to Verify Channel**\n\n"
            f"Error: {str(e)}\n\n"
            f"Please make sure the bot is an admin in the channel.",
            reply_to_message_id=message.id
        )

@app.on_message(filters.command("addpremium") & filters.private)
async def addpremium_command(client, message):
    """Handles the /addpremium command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply(
            "❌ Invalid command format.\n\n"
            "Usage: /addpremium [user_id] [plan_number]\n"
            "Use 0 for permanent premium\n\n"
            "Example: /addpremium 123456789 2 (for 1 month)\n"
            "Example: /addpremium 123456789 0 (for permanent)\n\n"
            "Available Plans:\n"
            "1 - 1 Day\n"
            "2 - 1 Month\n"
            "3 - 3 Months\n"
            "4 - 6 Months\n"
            "5 - 12 Months\n"
            "0 - Permanent",
            reply_to_message_id=message.id
        )
        return
    
    try:
        target_user_id = int(parts[1])
        plan_number = int(parts[2])
        
        # Define subscription plans locally to avoid scope issues
        subscription_plans = {
            1: {"name": "1 Day", "days": 1, "price": "₹10"},
            2: {"name": "1 Month", "days": 30, "price": "₹79"},
            3: {"name": "3 Months", "days": 90, "price": "₹199"},
            4: {"name": "6 Months", "days": 180, "price": "₹349"},
            5: {"name": "12 Months", "days": 365, "price": "₹599"}
        }
        
        # Get max duration from settings and format it
        max_duration_seconds = bot_settings.get("max_duration_seconds", 14400)
        max_duration_str = format_seconds(max_duration_seconds)
        
        # Calculate expiry date based on plan
        if plan_number == 0:
            # Permanent premium
            premium_expiry = None
            plan_name = "Permanent"
        elif plan_number in subscription_plans:
            # Get days from subscription plan
            days = subscription_plans[plan_number]["days"]
            plan_name = subscription_plans[plan_number]["name"]
            premium_expiry = get_ist_time() + timedelta(days=days)
        else:
            await message.reply(
                f"❌ Invalid plan number. Use 0 for permanent or 1-5 for subscription plans.\n\n"
                f"Available Plans:\n"
                f"1 - 1 Day (₹10)\n"
                f"2 - 1 Month (₹79)\n"
                f"3 - 3 Months (₹199)\n"
                f"4 - 6 Months (₹349)\n"
                f"5 - 12 Months (₹599)\n"
                f"0 - Permanent",
                reply_to_message_id=message.id
            )
            return
        
        # Update user in database
        result = users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"premium_expiry": premium_expiry}},
            upsert=True
        )
        
        if result.matched_count > 0 or result.upserted_id:
            # Get user info
            try:
                user_info = await client.get_users(target_user_id)
                user_mention = user_info.mention
            except:
                user_mention = f"User ID: {target_user_id}"
            
            await message.reply(
                f"✅ **Premium Added Successfully**\n\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **User ID:** `{target_user_id}`\n"
                f"⏰ **Plan:** {plan_name}\n\n"
                f"The user now has premium access.",
                reply_to_message_id=message.id
            )
            
            # Notify the user with the professional message (no buttons)
            try:
                await client.send_message(
                    target_user_id,
                    f"🎉 **Premium Access Granted!**\n\n"
                    f"You have been granted premium access for {plan_name}.\n\n"
                    f"**Enjoy Premium Features**\n\n"
                    f"• ♾️ Unlimited M3U8 recordings\n"
                    f"• 🎥 1 recording at a time\n"
                    f"• ⚡️ No queue – instant start\n"
                    f"• 🕒 Max Duration: {max_duration_str}\n"
                    f"• 🚀 Stable & fast processing\n"
                    f"• 🔓 Full access to all recorder features\n\n"
                    f"Thank you for choosing our service!\n\n"
                    f"💡 Use /myplan to view your subscription details"
                )
            except:
                pass  # User might have blocked the bot
            
            await log_activity(user_id, "addpremium", {
                "target_user_id": target_user_id,
                "plan": plan_name,
                "plan_number": plan_number
            })
        else:
            await message.reply(f"❌ Failed to add premium for user {target_user_id}.", reply_to_message_id=message.id)
            
    except ValueError:
        await message.reply("❌ Invalid user ID or plan number. Please provide valid numbers.", reply_to_message_id=message.id)
    except Exception as e:
        logger.error(f"Error in addpremium command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("removepremium") & filters.private)
async def removepremium_command(client, message):
    """Handles the /removepremium command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ Invalid command format.\n\n"
            "Usage: /removepremium [user_id]\n\n"
            "Example: /removepremium 123456789",
            reply_to_message_id=message.id
        )
        return
    
    try:
        target_user_id = int(parts[1])
        
        # Update user in database
        result = users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"premium_expiry": get_ist_time() - timedelta(days=1)}}  # Set to past date
        )
        
        if result.matched_count > 0:
            # Get user info
            try:
                user_info = await client.get_users(target_user_id)
                user_mention = user_info.mention
            except:
                user_mention = f"User ID: {target_user_id}"
            
            await message.reply(
                f"✅ **Premium Removed Successfully**\n\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **User ID:** `{target_user_id}`\n\n"
                f"The user no longer has premium access.",
                reply_to_message_id=message.id
            )
            
            # Notify the user
            try:
                await client.send_message(
                    target_user_id,
                    f"⚠️ **Premium Access Expired**\n\n"
                    f"Your premium access has expired.\n\n"
                    f"To renew your premium, use /subscription"
                )
            except:
                pass  # User might have blocked the bot
            
            await log_activity(user_id, "removepremium", {
                "target_user_id": target_user_id
            })
        else:
            await message.reply(f"❌ User {target_user_id} not found in database.", reply_to_message_id=message.id)
            
    except ValueError:
        await message.reply("❌ Invalid user ID. Please provide a valid number.", reply_to_message_id=message.id)
    except Exception as e:
        logger.error(f"Error in removepremium command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("premiumusers") & filters.private)
async def premiumusers_command(client, message):
    """Handles the /premiumusers command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    # Get all premium users
    premium_users = list(users_collection.find({
        "$or": [
            {"premium_expiry": None},  # Permanent premium
            {"premium_expiry": {"$gt": get_ist_time()}}  # Not expired
        ]
    }))
    
    if not premium_users:
        await message.reply("📋 **Premium Users List**\n\nNo premium users found.", reply_to_message_id=message.id)
        return
    
    response_text = "📋 **Premium Users List**\n\n"
    
    for user in premium_users:
        user_id_item = user.get("user_id")
        username = user.get("username", "Unknown")
        first_name = user.get("first_name", "Unknown")
        premium_expiry = user.get("premium_expiry")
        
        # Get user info from Telegram
        try:
            user_info = await client.get_users(user_id_item)
            user_mention = user_info.mention
        except:
            # Skip users with None user_id
            if user_id_item is None:
                continue
            user_mention = f"{first_name} (@{username})" if username != "Unknown" else first_name
        
        if premium_expiry is None:
            expiry_text = "Permanent"
        else:
            # Handle datetime comparison properly
            current_time = get_ist_time()
            if isinstance(premium_expiry, datetime) and premium_expiry.tzinfo is not None:
                premium_expiry = premium_expiry.replace(tzinfo=None)
            
            days_left = (premium_expiry - current_time).days
            expiry_text = f"{days_left} days left"
        
        response_text += f"👤 {user_mention}\n"
        response_text += f"🆔 ID: `{user_id_item}`\n"
        response_text += f"⏰ Expires: {expiry_text}\n\n"
    
    # Split message if too long
    if len(response_text) > 4000:
        parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
        for part in parts:
            await message.reply(part, disable_web_page_preview=True, reply_to_message_id=message.id)
    else:
        await message.reply(response_text, disable_web_page_preview=True, reply_to_message_id=message.id)
    
    await log_activity(user_id, "premiumusers", {"count": len(premium_users)})

@app.on_message(filters.command("ban") & filters.private)
async def ban_command(client, message):
    """Handles the /ban command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ Invalid command format.\n\n"
            "Usage: /ban [user_id]\n\n"
            "Example: /ban 123456789",
            reply_to_message_id=message.id
        )
        return
    
    try:
        target_user_id = int(parts[1])
        
        # Don't allow banning the owner
        if target_user_id == OWNER_ID:
            await message.reply("❌ You cannot ban the bot owner.", reply_to_message_id=message.id)
            return
        
        # Update user in database
        result = users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"is_banned": True}},
            upsert=True
        )
        
        if result.matched_count > 0 or result.upserted_id:
            # Get user info
            try:
                user_info = await client.get_users(target_user_id)
                user_mention = user_info.mention
            except:
                user_mention = f"User ID: {target_user_id}"
            
            await message.reply(
                f"✅ **User Banned Successfully**\n\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **User ID:** `{target_user_id}`\n\n"
                f"The user has been banned from using the bot.",
                reply_to_message_id=message.id
            )
            
            await log_activity(user_id, "ban", {
                "target_user_id": target_user_id
            })
        else:
            await message.reply(f"❌ Failed to ban user {target_user_id}.", reply_to_message_id=message.id)
            
    except ValueError:
        await message.reply("❌ Invalid user ID. Please provide a valid number.", reply_to_message_id=message.id)
    except Exception as e:
        logger.error(f"Error in ban command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("unban") & filters.private)
async def unban_command(client, message):
    """Handles the /unban command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ Invalid command format.\n\n"
            "Usage: /unban [user_id]\n\n"
            "Example: /unban 123456789",
            reply_to_message_id=message.id
        )
        return
    
    try:
        target_user_id = int(parts[1])
        
        # Update user in database
        result = users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"is_banned": False}}
        )
        
        if result.matched_count > 0:
            # Get user info
            try:
                user_info = await client.get_users(target_user_id)
                user_mention = user_info.mention
            except:
                user_mention = f"User ID: {target_user_id}"
            
            await message.reply(
                f"✅ **User Unbanned Successfully**\n\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **User ID:** `{target_user_id}`\n\n"
                f"The user has been unbanned and can now use the bot.",
                reply_to_message_id=message.id
            )
            
            await log_activity(user_id, "unban", {
                "target_user_id": target_user_id
            })
        else:
            await message.reply(f"❌ User {target_user_id} not found in database.", reply_to_message_id=message.id)
            
    except ValueError:
        await message.reply("❌ Invalid user ID. Please provide a valid number.", reply_to_message_id=message.id)
    except Exception as e:
        logger.error(f"Error in unban command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    """Handles the /stats command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    try:
        # Get user statistics
        total_users = users_collection.count_documents({})
        premium_users = users_collection.count_documents({
            "$or": [
                {"premium_expiry": None},  # Permanent premium
                {"premium_expiry": {"$gt": get_ist_time()}}  # Not expired
            ]
        })
        banned_users = users_collection.count_documents({"is_banned": True})
        
        # Get recording statistics
        total_recordings = recordings_collection.count_documents({})
        completed_recordings = recordings_collection.count_documents({"status": "completed"})
        active_recordings = len(bot_state.active_recordings)
        
        # Get storage statistics
        storage_info = "N/A"
        try:
            if os.path.exists(DOWNLOAD_PATH):
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(DOWNLOAD_PATH):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        total_size += os.path.getsize(fp)
                storage_info = format_bytes(total_size)
        except Exception as e:
            logger.error(f"Error calculating storage: {e}")
        
        stats_text = (
            f"📊 **Bot Statistics**\n\n"
            f"👥 **Users:**\n"
            f"• Total: `{total_users}`\n"
            f"• Premium: `{premium_users}`\n"
            f"• Banned: `{banned_users}`\n\n"
            f"🎬 **Recordings:**\n"
            f"• Total: `{total_recordings}`\n"
            f"• Completed: `{completed_recordings}`\n"
            f"• Active: `{active_recordings}`\n\n"
            f"💾 **Storage Used:** `{storage_info}`\n\n"
            f"🤖 **Bot Version:** `v1.0`\n"
            f"📦 **Pyrogram Version:** `{__version__}`"
        )
        
        await message.reply(stats_text, disable_web_page_preview=True, reply_to_message_id=message.id)
        await log_activity(user_id, "stats")
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("maintenance") & filters.private)
async def maintenance_command(client, message):
    """Handles the /maintenance command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ Invalid command format.\n\n"
            "Usage: /maintenance [on|off]\n\n"
            "Example: /maintenance on",
            reply_to_message_id=message.id
        )
        return
    
    try:
        status = parts[1].lower()
        
        if status not in ["on", "off"]:
            await message.reply("❌ Invalid status. Use 'on' or 'off'.", reply_to_message_id=message.id)
            return
        
        bot_state.maintenance_mode = (status == "on")
        
        status_text = "enabled" if bot_state.maintenance_mode else "disabled"
        await message.reply(
            f"✅ **Maintenance Mode {status_text.title()}**\n\n"
            f"The bot is now {'in maintenance mode' if bot_state.maintenance_mode else 'operational'}.\n\n"
            f"Only the owner can use the bot while in maintenance mode.",
            reply_to_message_id=message.id
        )
        
        await log_activity(user_id, "maintenance", {"status": status})
        
    except Exception as e:
        logger.error(f"Error in maintenance command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("logs") & filters.private)
async def logs_command(client, message):
    """Handles the /logs command (owner only)."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    parts = message.text.split(maxsplit=1)
    limit = 10  # Default limit
    
    if len(parts) >= 2:
        try:
            limit = int(parts[1])
            if limit <= 0 or limit > 100:
                await message.reply("❌ Limit must be between 1 and 100.", reply_to_message_id=message.id)
                return
        except ValueError:
            await message.reply("❌ Invalid limit. Please provide a valid number.", reply_to_message_id=message.id)
            return
    
    try:
        # Get recent logs from database
        logs = list(logs_collection.find().sort("timestamp", -1).limit(limit))
        
        if not logs:
            await message.reply("📋 **Recent Logs**\n\nNo logs found.", reply_to_message_id=message.id)
            return
        
        logs_text = f"📋 **Recent {len(logs)} Logs**\n\n"
        
        for log in logs:
            log_user_id = log.get("user_id", "Unknown")
            action = log.get("action", "Unknown")
            timestamp = log.get("timestamp", get_ist_time())
            details = log.get("details", {})
            
            # Format timestamp
            if isinstance(timestamp, datetime):
                timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            else:
                timestamp_str = str(timestamp)
            
            logs_text += f"🕐 **{timestamp_str}**\n"
            logs_text += f"👤 **User ID:** `{log_user_id}`\n"
            logs_text += f"🔧 **Action:** `{action}`\n"
            
            if details:
                logs_text += f"📝 **Details:**\n"
                for key, value in details.items():
                    logs_text += f"• {key}: `{value}`\n"
            
            logs_text += "\n"
        
        # Split message if too long
        if len(logs_text) > 4000:
            parts = [logs_text[i:i+4000] for i in range(0, len(logs_text), 4000)]
            for part in parts:
                await message.reply(part, disable_web_page_preview=True, reply_to_message_id=message.id)
        else:
            await message.reply(logs_text, disable_web_page_preview=True, reply_to_message_id=message.id)
        
        await log_activity(user_id, "logs", {"limit": limit})
        
    except Exception as e:
        logger.error(f"Error in logs command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {str(e)}", reply_to_message_id=message.id)

@app.on_message(filters.command("tasks") & filters.private)
async def tasks_command(client, message):
    """Handles the /tasks command (owner only) - shows all active recordings."""
    # Check authorization
    if not await check_authorization(client, message):
        return
    
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        await message.reply("❌ This command is only available to the bot owner.", reply_to_message_id=message.id)
        return
    
    # Get active recordings
    active_recordings = bot_state.get_active_recordings_details()
    
    if not active_recordings:
        await message.reply("📋 **Active Tasks**\n\nNo active recordings at the moment.", reply_to_message_id=message.id)
        return
    
    # Build tasks message
    tasks_text = "📋 **Active Recording Tasks**\n\n"
    
    for idx, recording in enumerate(active_recordings, 1):
        user_id_rec = recording["user_id"]
        filename = recording["filename"]
        
        # Get user info
        try:
            user = await client.get_users(user_id_rec)
            user_name = user.first_name or "Unknown"
            user_username = f"@{user.username}" if user.username else "No username"
        except:
            user_name = "Unknown"
            user_username = "No username"
        
        # Calculate elapsed time
        start_time = recording.get("start_time")
        if start_time:
            elapsed = datetime.now() - start_time
            elapsed_str = format_seconds(int(elapsed.total_seconds()))
        else:
            elapsed_str = "Unknown"
        
        tasks_text += (
            f"**{idx}. Task Details**\n"
            f"📁 **File:** `{filename}`\n"
            f"👤 **User:** {user_name} ({user_username})\n"
            f"🆔 **User ID:** `{user_id_rec}`\n"
            f"⏱️ **Elapsed:** {elapsed_str}\n\n"
        )
    
    await message.reply(tasks_text, reply_to_message_id=message.id)
    await log_activity(user_id, "tasks_viewed")

@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    """Handle callback queries from inline keyboards."""
    data = query.data
    
    if data == "about":
        await query.message.edit_text(
            text = f"<b>🤖 My Name :</b> <a href='https://t.me/M3U8_Recorder_07_Bot'>M3U8 Recorder Bot</a> \n<b>📝 Language :</b> <a href='https://python.org'>Python 3</a> \n<b>📚 Library :</b> <a href='https://pyrogram.org'>Pyrogram {__version__}</a> \n<b>🚀 Server :</b> <a href='https://heroku.com'>Heroku</a> \n<b>📢 Channel :</b> <a href='https://t.me/AniVerse4All'>AniVerse4All</a> \n<b>🧑‍💻 Developer :</b> <a href='tg://user?id={OWNER_ID}'>「𝗠𝗨𝗕𝗔」</a>",
            disable_web_page_preview = True,
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔒 Close", callback_data = "close")
                    ]
                ]
            )
        )
    elif data == "close":
        await query.message.delete()
        # Try to delete the user's command message if it exists
        if query.message.reply_to_message:
            try:
                await query.message.reply_to_message.delete()
            except:
                pass
    elif data == "settings_file_size":
        # Show file size options
        await query.message.edit_text(
            text="📁 **Select Maximum File Size**\n\nChoose the maximum file size for uploads:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("1GB", callback_data="set_file_size_1024"),
                    InlineKeyboardButton("2GB", callback_data="set_file_size_2048")
                ],
                [
                    InlineKeyboardButton("3GB", callback_data="set_file_size_3072"),
                    InlineKeyboardButton("4GB", callback_data="set_file_size_4096")
                ],
                [
                    InlineKeyboardButton("4GB+", callback_data="set_file_size_5120"),
                    InlineKeyboardButton("⬅️ Back", callback_data="settings_back")
                ]
            ])
        )
    elif data == "settings_tag":
        # Ask for new tag
        await query.message.edit_text(
            text="🏷️ **Custom Tag**\n\nCurrent tag: `" + bot_settings.get("custom_tag", "Madara2718") + "`\n\n" +
                 "Send the new tag as a message to this chat.\n\n" +
                 "The tag will be used in the filename format: [title].[date].[time].[quality].TV-DL.[languages].[format].[channels].[codec]-[tag].mkv",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")]
            ])
        )
        
        # Add this user to pending tag updates list
        bot_state.pending_tag_updates[query.from_user.id] = query.message.id
    # NEW: Handle upload destination setting
    elif data == "settings_upload_destination":
        # Show upload destination options
        await query.message.edit_text(
            text="☁️ **Select Upload Destination**\n\nChoose where to upload recorded files:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Telegram (as media)", callback_data="set_upload_destination_telegram"),
                    InlineKeyboardButton("Gofile (link)", callback_data="set_upload_destination_gofile")
                ],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="settings_back")
                ]
            ])
        )
    # NEW: Handle max duration setting
    elif data == "settings_max_duration":
        # Ask for new max duration
        await query.message.edit_text(
            text="⏱️ **Maximum Recording Duration**\n\nCurrent maximum: " + 
                 format_seconds(bot_settings.get("max_duration_seconds", 14400)) + "\n\n" +
                 "Send the new maximum duration in HH:MM:SS format as a message to this chat.\n\n" +
                 "Example: 02:30:00 for 2 hours and 30 minutes",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")]
            ])
        )
        
        # Add this user to pending duration updates list
        bot_state.pending_duration_updates[query.from_user.id] = query.message.id
    elif data == "settings_back":
        # Go back to main settings
        await show_main_settings(client, query.message)
    elif data == "settings_dbchannel":
        # Show database channel settings
        db_channel_info = get_db_channel_info()
        channel_id = db_channel_info.get("channel_id")
        channel_name = db_channel_info.get("channel_name", "Not Set")
        verified = db_channel_info.get("verified", False)
        
        channel_status = "✅ Verified" if verified else "❌ Not verified"
        
        await query.message.edit_text(
            text=f"📢 **Database Channel Settings**\n\n"
                 f"• ID: `{channel_id}`\n"
                 f"• Name: {channel_name}\n"
                 f"• Status: {channel_status}\n\n"
                 f"Use /setdbchannel to update the database channel.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")]
            ])
        )
    # NEW: Handle upload destination setting
    elif data.startswith("set_upload_destination_"):
        # Update upload destination setting
        destination = data.split("_")[3]
        update_bot_setting("upload_destination", destination)
        
        destination_display = "Telegram (as media)" if destination == "telegram" else "Gofile (link)"
        await query.answer(f"✅ Upload destination set to {destination_display}")
        
        # Go back to main settings
        await show_main_settings(client, query.message)
    
    await log_activity(query.from_user.id, "callback", {"data": data})

async def process_completed_recording(client, message, status_msg, output_file, thumbnail_file, filename, user_id, recording_id, cancelled=False):
    """Process and upload completed recording with robust error handling."""
    try:
        status_text = "✅ **Recording Complete!**" if not cancelled else "🚫 **Recording Cancelled**"
        await status_msg.edit(f"{status_text}\n\n🔄 Processing file details...")
        
        # Get file information
        if not os.path.exists(output_file):
            logger.error(f"Output file not found: {output_file}")
            return
            
        file_size = os.path.getsize(output_file)
        
        
        # Get actual duration
        actual_duration = 0
        try:
            probe_cmd = [FFPROBE_PATH, "-v", "error", "-show_format", "-print_format", "json", output_file]
            stdout, _, returncode = await run_cmd(probe_cmd)
            if returncode == 0 and stdout:
                try:
                    format_data = json.loads(stdout)
                    actual_duration = int(float(format_data.get("format", {}).get("duration", 0)))
                except:
                    pass
        except:
            pass
        
        # Generate thumbnail
        generated_thumbnail = None
        try:
            thumbnail_cmd = [FFMPEG_PATH, "-y", "-i", output_file, "-ss", "00:00:10", "-vframes", "1", "-q:v", "3", thumbnail_file]
            _, _, thumb_returncode = await run_cmd(thumbnail_cmd, timeout=30)
            generated_thumbnail = thumbnail_file if thumb_returncode == 0 and os.path.exists(thumbnail_file) else None
        except:
            pass
        
        GOFILE_THRESHOLD = 1.95 * 1024 * 1024 * 1024  # 1.95GB in bytes
        
        # Get upload destination from settings, but override if file is too large
        upload_destination = bot_settings.get("upload_destination", "telegram")
        force_gofile = file_size > GOFILE_THRESHOLD
        
        if force_gofile and upload_destination == "telegram":
            upload_destination = "gofile"
            logger.info(f"File size {format_bytes(file_size)} exceeds 1.95GB - forcing GoFile upload")
        
        # Update status message
        status_prefix = "⬆️ **Uploading Recording**" if not cancelled else "⬆️ **Uploading Cancelled Recording**"
        upload_info = ""
        if force_gofile:
            upload_info = "\n⚠️ **File size > 1.95GB - uploading to GoFile**"
        
        await status_msg.edit(
            f"{status_prefix}\n\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{format_bytes(file_size)}`\n"
            f"⏱️ **Duration:** `{format_seconds(actual_duration)}`{upload_info}\n"
            f"🔄 **Uploading to {'Telegram' if upload_destination == 'telegram' else 'GoFile'}...**"
        )
        
        if upload_destination == "telegram":
            # Upload to Telegram
            try:
                # Create caption
                caption_prefix = "📹" if not cancelled else "🚫"
                caption = f"<b>{caption_prefix} {filename}</b>\n\n💾 Size: {format_bytes(file_size)}\n⏱️ Duration: {format_seconds(actual_duration)}"
                
                if cancelled:
                    caption += "\n\n⚠️ This recording was cancelled before completion."
                
                upload_attempts = 3
                sent_message = None
                
                for attempt in range(upload_attempts):
                    try:
                        with open(output_file, 'rb') as video_file:
                            thumb_file = None
                            if generated_thumbnail and os.path.exists(generated_thumbnail):
                                thumb_file = open(generated_thumbnail, 'rb')
                            
                            try:
                                # Upload as a reply to the original command message
                                sent_message = await client.send_video(
                                    chat_id=message.chat.id,
                                    video=video_file,
                                    caption=caption,
                                    parse_mode=ParseMode.HTML,
                                    file_name=filename,
                                    thumb=thumb_file,
                                    duration=actual_duration,
                                    disable_notification=False,
                                    reply_to_message_id=message.id
                                )
                                break  # Success
                            finally:
                                if thumb_file:
                                    thumb_file.close()
                    
                    except Exception as upload_error:
                        logger.error(f"Upload attempt {attempt + 1} failed: {upload_error}")
                        if attempt < upload_attempts - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            raise upload_error
                
                if sent_message:
                    logger.info(f"Recording uploaded successfully to Telegram: {filename}")
                    
                    await forward_to_database_channel(client, sent_message, actual_duration)
                    
                    try:
                        await status_msg.delete()
                    except:
                        pass
                    
                    # Log activity
                    await log_activity(user_id, "recording_completed" if not cancelled else "recording_cancelled", {
                        "filename": filename,
                        "duration": actual_duration,
                        "file_size": file_size,
                        "upload_destination": "telegram",
                        "message_id": sent_message.id
                    })
                    
                    # Update database
                    if recording_id:
                        recordings_collection.update_one(
                            {"recording_id": recording_id},
                            {"$set": {"status": "uploaded" if not cancelled else "cancelled_uploaded", "uploaded_at": get_ist_time()}}
                        )
            
            except Exception as e:
                logger.error(f"Error uploading to Telegram: {e}", exc_info=True)
                try:
                    await status_msg.edit(
                        f"❌ **Upload Failed**\n\n"
                        f"Error: {str(e)[:150]}\n\n"
                        f"Please try again or contact @II_Madara_II"
                    )
                except MessageNotModified:
                    pass
                except Exception as edit_error:
                    logger.warning(f"Could not edit status message after Telegram upload failure: {edit_error}")
        
        elif upload_destination == "gofile":
            # Upload to Gofile
            try:
                # Upload file to Gofile with progress tracking
                upload_result = await upload_to_gofile(output_file, status_msg, filename)
                
                if upload_result.get("success"):
                    download_link = upload_result.get("download_link")
                    file_name = upload_result.get("file_name", filename)
                    
                    # Create message with download link
                    caption_prefix = "📹" if not cancelled else "🚫"
                    caption = (
                        f"<b>{caption_prefix} {file_name}</b>\n\n"
                        f"💾 Size: {format_bytes(file_size)}\n"
                        f"⏱️ Duration: {format_seconds(actual_duration)}\n\n"
                        f"🔗 <a href='{download_link}'>Download from GoFile</a>"
                    )
                    
                    if cancelled:
                        caption += "\n\n⚠️ This recording was cancelled before completion."
                    
                    if force_gofile:
                        caption += "\n\nℹ️ File was automatically uploaded to GoFile due to size > 1.95GB"
                    
                    # Send message with download link
                    sent_message = await client.send_message(
                        chat_id=message.chat.id,
                        text=caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                        reply_to_message_id=message.id
                    )
                    
                    logger.info(f"Recording uploaded successfully to Gofile: {filename}")
                    
                    await send_gofile_to_database_channel(client, message.chat.id, file_name, download_link, file_size, actual_duration)
                    
                    try:
                        await status_msg.delete()
                    except:
                        pass
                    
                    # Log activity
                    await log_activity(user_id, "recording_completed" if not cancelled else "recording_cancelled", {
                        "filename": filename,
                        "duration": actual_duration,
                        "file_size": file_size,
                        "upload_destination": "gofile",
                        "download_link": download_link,
                        "file_name": file_name, # Added this for clarity
                        "forced_gofile": force_gofile
                    })
                    
                    # Update database
                    if recording_id:
                        recordings_collection.update_one(
                            {"recording_id": recording_id},
                            {"$set": {"status": "uploaded" if not cancelled else "cancelled_uploaded", "uploaded_at": get_ist_time()}}
                        )
                else:
                    error_msg = upload_result.get("error", "Unknown error")
                    logger.error(f"Error uploading to Gofile: {error_msg}")
                    try:
                        await status_msg.edit(
                            f"❌ **Upload Failed**\n\n"
                            f"GoFile upload error: {error_msg}\n\n"
                            f"Please try again or contact @II_Madara_II"
                        )
                    except MessageNotModified:
                        pass
                    except Exception as edit_error:
                        logger.warning(f"Could not edit status message after GoFile upload failure: {edit_error}")
            
            except Exception as e:
                logger.error(f"Error uploading to Gofile: {e}", exc_info=True)
                try:
                    await status_msg.edit(
                        f"❌ **Upload Failed**\n\n"
                        f"Error: {str(e)[:150]}\n\n"
                        f"Please try again or contact @II_Madara_II"
                    )
                except MessageNotModified:
                    pass
                except Exception as edit_error:
                    logger.warning(f"Could not edit status message after GoFile upload failure: {edit_error}")

    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        try:
            await status_msg.edit(
                f"❌ **Upload Failed**\n\n"
                f"Error: {str(e)[:150]}\n\n"
                f"Please try again or contact @II_Madara_II"
            )
        except MessageNotModified:
            pass
        except Exception as edit_error:
            logger.warning(f"Could not edit status message after general processing failure: {edit_error}")
    
    finally:
        # Cleanup files safely
        await cleanup_files(output_file, thumbnail_file)

async def start_recording(client, message, url, duration_seconds, title):
    """Start recording process with proper stream type detection."""
    user_id = message.from_user.id
    start_time = get_ist_time()
    
    # Create status message
    status_msg = await message.reply("🔍 **Analyzing Stream...**\n\nPlease wait while I check stream details.", reply_to_message_id=message.id)
    
    output_file = None
    thumbnail_file = None
    recording_id = None
    
    try:
        stream_info = await get_stream_info(url)
        stream_type = stream_info.get('stream_type', 'm3u8')
        
        # Generate filename with correct extension
        filename = generate_filename(
            title=title,
            start_time=start_time,
            duration_seconds=duration_seconds,
            quality=stream_info['video_quality'],
            audio_languages=stream_info.get('audio_languages_ordered', stream_info['audio_languages']),  # Use ordered if available
            audio_format=stream_info['audio_formats'][0] if stream_info['audio_formats'] else "AAC",
            audio_channels=stream_info['audio_channels'],
            video_codec=stream_info['video_codec'],
            stream_type=stream_type
        )
        
        output_file = os.path.join(DOWNLOAD_PATH, filename)
        thumbnail_file = os.path.join(DOWNLOAD_PATH, f"{os.path.splitext(filename)[0]}.jpg")
        
        # Ensure download directory exists
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Update status with stream info
        stream_details = (
            f"🎬 **Recording Started**\n\n"
            f"📺 **Title:** `{title}`\n"
            f"🎥 **Quality:** `{stream_info['video_quality']}`\n"
            f"🔊 **Audio:** `{'Yes' if stream_info['audio_present'] else 'No'}`\n"
            f"🌐 **Languages:** `{', '.join(stream_info.get('audio_languages_ordered', stream_info['audio_languages'])) if stream_info.get('audio_languages_ordered', stream_info['audio_languages']) else 'Unknown'}`\n"
            f"🎯 **Stream Type:** `{stream_type.upper()}`\n"
            f"⏱️ **Duration:** `{format_seconds(duration_seconds)}`\n"
            f"📁 **Output:** `{filename}`\n\n"
            f"🚀 **Starting recording...**"
        )
        
        await status_msg.edit(stream_details)
        
        # Generate unique recording ID
        recording_id = f"{user_id}_{start_time.timestamp()}"
        
        # Add to active recordings
        recording_info = {
            'user_id': user_id,
            'recording_id': recording_id,
            'filename': output_file,
            'thumbnail': thumbnail_file,
            'title': title,
            'start_time': start_time,
            'duration': duration_seconds,
            'url': url,
            'status_msg_id': status_msg.id,
            'chat_id': message.chat.id,
            'stream_type': stream_type,
            'quality': stream_info['video_quality'],
            'audio_languages': stream_info.get('audio_languages_ordered', stream_info['audio_languages']),
            'audio_format': stream_info['audio_formats'][0] if stream_info['audio_formats'] else "AAC",
            'audio_channels': stream_info['audio_channels'],
            'video_codec': stream_info['video_codec']
        }
        bot_state.add_recording(user_id, recording_info)
        
        # Save to database with unique recording_id
        try:
            recordings_collection.insert_one({
                **recording_info,
                "status": "recording",
                "created_at": get_ist_time()
            })
        except pymongo.errors.DuplicateKeyError:
            logger.error(f"Duplicate key error for recording_id: {recording_id}. Generating a new one.")
            # Generate a new ID with random component
            recording_id = f"{user_id}_{start_time.timestamp()}_{uuid.uuid4().hex[:8]}"
            recording_info['recording_id'] = recording_id
            recordings_collection.insert_one({
                **recording_info,
                "status": "recording",
                "created_at": get_ist_time()
            })
        
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        
        ffmpeg_cmd = [
            FFMPEG_PATH, "-y",
            "-nostdin",
            "-hide_banner", "-loglevel", "error",
            "-rw_timeout", "15000000",
            "-user_agent", user_agent,
            "-reconnect", "1", "-reconnect_streamed", "1",
            "-reconnect_delay_max", "10",
            "-fflags", "+genpts+discardcorrupt+igndts+flush_packets",
            "-analyzeduration", "10000000",
            "-probesize", "10000000",
            "-err_detect", "ignore_err",
            "-i", url,
            "-t", str(int(duration_seconds)),
            "-c", "copy",
            "-map", "0",
            "-map_metadata", "0",
            "-map", "-0:d",
            "-f", "matroska",
            "-metadata", f"title={title}",
            "-metadata", f"encoder=M3U8 Recorder Bot by {bot_settings.get('custom_tag', 'Madara2718')}",
            "-metadata", f"creation_time={start_time.isoformat()}",
            output_file
        ]
        
        logger.info(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # Execute FFmpeg with proper process management
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        bot_state.recording_processes[user_id] = process
        
        # Start progress tracking
        progress_task = asyncio.create_task(
            track_recording_progress(client, message.chat.id, status_msg.id, user_id, output_file, duration_seconds, recording_id)
        )
        bot_state.progress_trackers[user_id] = progress_task
        
        # Wait for process completion
        stdout, stderr = await process.communicate()
        
        logger.info(f"FFmpeg process completed with return code: {process.returncode}")
        
        # Remove from active recordings
        bot_state.remove_recording(user_id)
        
        # Update database
        if recording_id:
            recordings_collection.update_one(
                {"recording_id": recording_id},
                {"$set": {"status": "completed", "completed_at": get_ist_time()}}
            )
        
        # Check if recording was successful
        file_exists = os.path.exists(output_file)
        file_size = os.path.getsize(output_file) if file_exists else 0
        
        logger.info(f"Recording file check - Exists: {file_exists}, Size: {file_size}")
        
        # Process completed file if it has content
        if file_exists and file_size > 1000:  # At least 1KB
            await process_completed_recording(client, message, status_msg, output_file, thumbnail_file, filename, user_id, recording_id)
        else:
            logger.error(f"Recording failed - File doesn't exist or too small")
            await status_msg.edit(
                f"❌ **Recording Failed**\n\n"
                f"The stream recording encountered an issue.\n\n"
                f"Possible reasons:\n"
                f"• The URL is blocked or geo-restricted\n"
                f"• The stream went offline\n"
                f"• Connection was unstable\n"
                f"• Stream format not supported\n\n"
                f"Please verify the URL and try again."
            )
            await cleanup_files(output_file, thumbnail_file)
        
    except asyncio.CancelledError:
        logger.info(f"Recording cancelled for user {user_id}")
        try:
            await status_msg.edit("🚫 **Recording Cancelled**\n\nThe recording was cancelled by user request.")
            
            # Delete the status message after a short delay
            await asyncio.sleep(3)
            await status_msg.delete()
        except MessageNotModified:
            pass
        except Exception as e:
            logger.warning(f"Could not edit or delete status message after cancellation: {e}")
            
        bot_state.remove_recording(user_id)
        if recording_id:
            recordings_collection.update_one(
                {"recording_id": recording_id},
                {"$set": {"status": "cancelled", "cancelled_at": get_ist_time()}}
            )
        await cleanup_files(output_file, thumbnail_file)
    except Exception as e:
        logger.error(f"Unexpected error in start_recording: {e}", exc_info=True)
        try:
            await status_msg.edit(f"❌ **Unexpected Error**\n\n`{str(e)[:200]}`")
        except MessageNotModified:
            pass
        except Exception as edit_error:
            logger.warning(f"Could not edit status message after unexpected error: {edit_error}")
            
        bot_state.remove_recording(user_id)
        if recording_id:
            recordings_collection.update_one(
                {"recording_id": recording_id},
                {"$set": {"status": "failed", "failed_at": get_ist_time(), "error": str(e)}}
            )
        await cleanup_files(output_file, thumbnail_file)

async def track_recording_progress(client, chat_id, status_msg_id, user_id, output_file, total_duration, recording_id):
    """Track recording progress and update status message."""
    start_time = time.time()
    last_update_time = 0
    
    try:
        while user_id in bot_state.active_recordings:
            await asyncio.sleep(10)  # Update every 10 seconds
            
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Skip if file doesn't exist yet or is being processed by cancellation logic
            if not os.path.exists(output_file) or user_id not in bot_state.active_recordings:
                continue
            
            # Check if recording still exists in database and is in 'recording' state
            if recording_id:
                recording = recordings_collection.find_one({"recording_id": recording_id})
                if not recording or recording.get("status") != "recording":
                    logger.info(f"Recording {recording_id} no longer in 'recording' state in DB.")
                    break
            
            try:
                file_size = os.path.getsize(output_file)
                
                # Calculate progress
                progress_percent = min((elapsed / total_duration) * 100, 100)
                
                # Create progress bar
                filled_blocks = int(progress_percent // 5)
                progress_bar = "█" * filled_blocks + "░" * (20 - filled_blocks)
                
                # Update message every 30 seconds or significant progress change
                if current_time - last_update_time >= 30 or abs(progress_percent - (last_update_time * 100 / 5)) >= 10: # Check against last recorded percentage
                    progress_text = (
                        f"🎬 **Recording in Progress**\n\n"
                        f"📊 **Progress:** `{progress_percent:.1f}%`\n"
                        f"`{progress_bar}`\n\n"
                        f"⏱️ **Elapsed:** `{format_seconds(int(elapsed))}`\n"
                        f"📁 **File Size:** `{format_bytes(file_size)}`\n"
                        f"🎯 **ETA:** `{format_seconds(int(total_duration - elapsed)) if elapsed < total_duration else 'Finishing...'}`\n\n"
                    )
                    
                    try:
                        await client.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg_id,
                            text=progress_text
                        )
                        last_update_time = current_time
                    except MessageNotModified:
                        pass # Ignore if message content hasn't changed
                    except Exception as e:
                        logger.error(f"Failed to update progress message: {e}")
                        
            except Exception as e:
                logger.error(f"Error during progress tracking: {e}", exc_info=True)
                
    except asyncio.CancelledError:
        logger.info(f"Progress tracker for user {user_id} cancelled.")
        pass # Task was cancelled

@app.on_message(filters.text & filters.private)
async def handle_text_messages(client, message):
    """Handle text messages for settings updates."""
    user_id = message.from_user.id
    
    # Check if user has pending tag update
    if user_id in bot_state.pending_tag_updates:
        message_id = bot_state.pending_tag_updates[user_id]
        new_tag = message.text.strip()
        
        # Basic validation
        if not new_tag:
            await message.reply("❌ Tag cannot be empty. Please provide a valid tag.", reply_to_message_id=message.id)
            return
        if len(new_tag) > 20:
            await message.reply("❌ Tag is too long. Please use a tag with 20 characters or less.", reply_to_message_id=message.id)
            return
        
        # Update bot setting
        update_bot_setting("custom_tag", new_tag)
        
        # Remove from pending updates
        del bot_state.pending_tag_updates[user_id]
        
        # Delete user's message
        try:
            await message.delete()
        except:
            pass
        
        # Update settings message
        try:
            settings_message = await client.get_messages(message.chat.id, message_id)
            await settings_message.edit_text(
                text=f"✅ Custom tag updated to: `{new_tag}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to update settings message after tag update: {e}")
        
        return
    
    # Check if user has pending duration update
    if user_id in bot_state.pending_duration_updates:
        message_id = bot_state.pending_duration_updates[user_id]
        duration_text = message.text.strip()
        
        # Parse duration (HH:MM:SS)
        try:
            parts = duration_text.split(":")
            if len(parts) != 3:
                raise ValueError("Invalid format")
            
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            
            total_seconds = hours * 3600 + minutes * 60 + seconds
            
            if total_seconds <= 0:
                raise ValueError("Duration must be positive")
            
            # Update bot setting
            update_bot_setting("max_duration_seconds", total_seconds)
            
            # Remove from pending updates
            del bot_state.pending_duration_updates[user_id]
            
            # Delete user's message
            try:
                await message.delete()
            except:
                pass
            
            # Update settings message
            try:
                settings_message = await client.get_messages(message.chat.id, message_id)
                await settings_message.edit_text(
                    text=f"✅ Maximum duration updated to: `{duration_text}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to update settings message after duration update: {e}")
        except ValueError as e:
            # Delete user's message
            try:
                await message.delete()
            except:
                pass
            
            # Show error
            try:
                settings_message = await client.get_messages(message.chat.id, message_id)
                await settings_message.edit_text(
                    text=f"❌ Invalid duration format. Please use HH:MM:SS format.\n\nExample: 02:30:00",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to edit settings message with duration error: {e}")
        
        return
    
    # If no pending updates, assume it's a regular message and ignore or provide help
    # For now, we'll just ignore other text messages to avoid clutter.

# NEW: Bot initialization function
async def initialize_bot(client):
    """Initialize bot and verify connections."""
    logger.info("Initializing bot...")
    
    # Wait for bot to be ready
    if not await ensure_bot_ready(client, max_retries=10, delay=3):
        logger.error("Bot failed to initialize properly")
        return False
    
    # Verify database channel access
    db_channel_info = get_db_channel_info()
    channel_id = db_channel_info.get("channel_id")
    
    if channel_id:
        try:
            chat = await client.get_chat(channel_id)
            logger.info(f"Database channel verified: {chat.title}")
            
            # Update channel info in MongoDB
            db_channel_info.update({
                "channel_id": channel_id,
                "channel_name": chat.title,
                "verified": True,
                "last_verified": get_ist_time().isoformat()
            })
            update_db_channel_info(db_channel_info)
        except Exception as e:
            logger.error(f"Database channel access failed: {e}")
            
            # Mark as unverified in MongoDB
            db_channel_info["verified"] = False
            db_channel_info["last_error"] = str(e)
            db_channel_info["last_error_time"] = get_ist_time().isoformat()
            update_db_channel_info(db_channel_info)
    
    logger.info("Bot initialization complete")
    return True

# Start bot
if __name__ == "__main__":
    logger.info("Starting bot...")
    
    async def main():
        async with app:
            # Initialize bot
            if not await initialize_bot(app):
                logger.error("Bot initialization failed")
                return
            
            # Keep the bot running
            logger.info("Bot is now running...")
            await idle()
    
    # Run the bot
    app.run(main())
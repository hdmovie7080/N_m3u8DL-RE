"""
SONY YAY! SonyLIV Recording Telegram Bot
Records SONY YAY streams using ffmpeg or N_m3u8DL-RE
"""

import asyncio
import os
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiofiles
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, BotCommand
)
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.enums import ParseMode
from dotenv import load_dotenv

from recording import RecorderFactory
from file_handler import initialize_handlers

# Load environment variables
load_dotenv()

# --- Configuration ---
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
GOFILE_TOKEN = os.getenv("GOFILE_TOKEN", "")
SONY_STREAM_URL = os.getenv("SONY_STREAM_URL", "https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "./recordings")
MAX_CONCURRENT_RECORDINGS = int(os.getenv("MAX_CONCURRENT_RECORDINGS", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Validate required configuration
if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
    logging.error("Missing required configuration. Please check your .env file.")
    sys.exit(1)

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sony_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Pyrogram client
app = Client(
    "sony_yay_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4,
    sleep_threshold=0
)

# Global handlers (initialized during startup)
file_handler = None
recording_manager = None

# User states for tracking recording progress
user_states = {}  # user_id -> {"recording_method": "", "delivery_method": "", "message_id": int}


def get_user_state(user_id: int) -> dict:
    """Get or create user state."""
    if user_id not in user_states:
        user_states[user_id] = {
            "recording_method": None,
            "delivery_method": None,
            "duration": None,
            "message_id": None,
            "recording_task": None,
            "recorder": None
        }
    return user_states[user_id]


def clear_user_state(user_id: int):
    """Clear user state."""
    if user_id in user_states:
        del user_states[user_id]


def parse_duration(duration_str: str) -> Optional[str]:
    """
    Validate and parse duration string in HH:MM:SS format.
    Returns the duration string if valid, None otherwise.
    """
    try:
        parts = duration_str.strip().split(':')
        if len(parts) != 3:
            return None
        
        hours, minutes, seconds = map(int, parts)
        
        # Validate ranges
        if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            return None
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except (ValueError, AttributeError):
        return None


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command."""
    welcome_text = """
🎬 **SONY YAY! Recording Bot**

Welcome! This bot records SONY YAY! SonyLIV streams.

**Commands:**
`/record HH:MM:SS` - Start recording with duration (e.g., /record 01:30:45)
`/help` - Show this help message
`/about` - About this bot

**Stream:** SONY YAY! SonyLIV
**URL:** `https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8`

Use `/record 01:30:45` to start recording!
    """
    await message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command."""
    help_text = """
📖 **SONY YAY! Recording Bot - Help**

**How to use:**

1. Send `/record HH:MM:SS` to start recording
   Example: `/record 01:30:45` (records for 1 hour 30 minutes 45 seconds)

2. Choose your recording method:
   - **FFmpeg** - Direct stream recording (faster)
   - **N_m3u8DL-RE** - Advanced M3U8 downloader

3. Choose how to receive the file:
   - **Telegram Upload** - Direct file upload to Telegram
   - **GoFile Link** - Download link via GoFile

4. Bot will start recording and show progress
5. Once complete, file will be uploaded

**Valid Duration Format:** HH:MM:SS
- HH: Hours (00-23)
- MM: Minutes (00-59)
- SS: Seconds (00-59)

**Example:** `/record 02:15:30` - records for 2 hours, 15 minutes, 30 seconds
    """
    await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("about"))
async def about_command(client: Client, message: Message):
    """Handle /about command."""
    about_text = """
ℹ️ **About SONY YAY! Recording Bot**

**Version:** 1.0.0
**Stream:** SONY YAY! SonyLIV
**Recording Methods:** FFmpeg, N_m3u8DL-RE
**Delivery Methods:** Telegram Direct Upload, GoFile

**Features:**
✅ Dual recording methods for reliability
✅ Real-time progress updates
✅ Multiple delivery options
✅ Automatic file cleanup
✅ Concurrent recording support

**Developer:** Made with ❤️

**Status:** Active and Running ✅
    """
    await message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("record"))
async def record_command(client: Client, message: Message):
    """Handle /record HH:MM:SS command."""
    user_id = message.from_user.id
    
    # Check if user already has active recording
    if recording_manager.is_user_recording(user_id):
        await message.reply_text("⚠️ You already have an active recording. Please wait for it to complete.")
        return
    
    # Parse duration from command
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text(
            "❌ Invalid format!\n\n`/record HH:MM:SS`\n\n"
            "Example: `/record 01:30:45`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    duration = parse_duration(args[1])
    if not duration:
        await message.reply_text(
            "❌ Invalid duration format!\n\n"
            "Use `HH:MM:SS` format (e.g., `01:30:45`)\n"
            "- HH: 00-23 (hours)\n"
            "- MM: 00-59 (minutes)\n"
            "- SS: 00-59 (seconds)",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check remaining slots
    remaining = recording_manager.get_remaining_slots()
    if remaining <= 0:
        await message.reply_text(
            f"❌ No available recording slots!\n"
            f"Maximum concurrent recordings: {recording_manager.max_concurrent}\n"
            f"Please try again later."
        )
        return
    
    # Store user state
    state = get_user_state(user_id)
    state["duration"] = duration
    
    # Ask for recording method
    method_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 FFmpeg", callback_data="method_ffmpeg"),
            InlineKeyboardButton("📥 N_m3u8DL-RE", callback_data="method_n_m3u8dl")
        ]
    ])
    
    msg = await message.reply_text(
        f"📹 **Recording Duration:** `{duration}`\n\n"
        f"Choose your recording method:",
        reply_markup=method_keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    state["message_id"] = msg.id


@app.on_callback_query(filters.regex("^method_"))
async def method_callback(client: Client, callback_query: CallbackQuery):
    """Handle recording method selection."""
    user_id = callback_query.from_user.id
    state = get_user_state(user_id)
    
    method = callback_query.data.replace("method_", "").upper()
    if method == "N_M3U8DL":
        method = "N_m3u8DL-RE"
    
    state["recording_method"] = method
    
    try:
        await callback_query.message.edit_text(
            f"📹 **Recording Duration:** `{state['duration']}`\n"
            f"**Method:** `{method}`\n\n"
            f"How would you like to receive the file?"
        )
    except MessageNotModified:
        pass
    
    # Ask for delivery method
    delivery_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Telegram Upload", callback_data="delivery_telegram"),
        ],
        [
            InlineKeyboardButton("🔗 GoFile Link", callback_data="delivery_gofile"),
        ]
    ])
    
    await callback_query.message.reply_text(
        "Choose delivery method:",
        reply_markup=delivery_keyboard
    )


@app.on_callback_query(filters.regex("^delivery_"))
async def delivery_callback(client: Client, callback_query: CallbackQuery):
    """Handle delivery method selection."""
    user_id = callback_query.from_user.id
    state = get_user_state(user_id)
    
    delivery = callback_query.data.replace("delivery_", "").lower()
    state["delivery_method"] = delivery
    
    try:
        await callback_query.message.edit_text(
            f"📹 **Duration:** `{state['duration']}`\n"
            f"**Method:** `{state['recording_method']}`\n"
            f"**Delivery:** `{delivery.upper()}`\n\n"
            f"Starting recording... ⏳"
        )
    except MessageNotModified:
        pass
    
    # Start recording
    await start_recording(client, callback_query.message, user_id, state)


async def start_recording(client: Client, message: Message, user_id: int, state: dict):
    """Start the actual recording process."""
    try:
        # Acquire recording slot
        acquired = await recording_manager.acquire(user_id)
        if not acquired:
            await message.reply_text("❌ Failed to acquire recording slot. Please try again.")
            clear_user_state(user_id)
            return
        
        duration = state["duration"]
        method = state["recording_method"]
        delivery = state["delivery_method"]
        
        # Create output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{RECORDINGS_DIR}/SONY_YAY_{timestamp}.mkv"
        Path(RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)
        
        # Create recorder instance
        recorder = RecorderFactory.create(method, SONY_STREAM_URL, duration, output_file)
        state["recorder"] = recorder
        
        # Progress update callback
        last_update = [time.time()]
        
        async def progress_callback(progress: dict):
            """Update progress in message."""
            current_time = time.time()
            if current_time - last_update[0] < 5:  # Update every 5 seconds
                return
            
            last_update[0] = current_time
            percent = progress.get("percent", 0)
            elapsed = progress.get("elapsed", "00:00:00")
            total = progress.get("total", "00:00:00")
            
            try:
                await message.edit_text(
                    f"🎬 **SONY YAY! Recording**\n\n"
                    f"📊 **Progress:** {percent}%\n"
                    f"⏱️ **Elapsed:** {elapsed}/{total}\n"
                    f"🔧 **Method:** {method}\n"
                    f"📤 **Delivery:** {delivery.upper()}\n\n"
                    f"Recording in progress... ⏳"
                )
            except MessageNotModified:
                pass
            except Exception as e:
                logger.error(f"Error updating progress: {e}")
        
        # Start recording
        logger.info(f"Starting {method} recording for user {user_id}: {duration}")
        
        success = await recorder.record(progress_callback=progress_callback)
        
        if not success:
            if recorder.cancelled:
                await message.edit_text("❌ Recording was cancelled.")
            else:
                await message.edit_text(
                    f"❌ Recording failed!\n\n"
                    f"Please check the logs for more details."
                )
            clear_user_state(user_id)
            await recording_manager.release(user_id)
            return
        
        # File recording completed
        await message.edit_text(
            f"✅ Recording completed!\n"
            f"📁 File size: {file_handler.get_file_size_mb(output_file):.2f} MB\n\n"
            f"Uploading file... ⏳"
        )
        
        # Upload based on delivery method
        if delivery == "telegram":
            await upload_to_telegram(client, message, output_file, user_id)
        elif delivery == "gofile":
            await upload_to_gofile(message, output_file, user_id)
        
    except Exception as e:
        logger.error(f"Recording error for user {user_id}: {e}")
        await message.reply_text(f"❌ Error during recording: {str(e)}")
    finally:
        # Cleanup
        state_copy = state.copy()
        clear_user_state(user_id)
        await recording_manager.release(user_id)
        
        # Delete recording file if it exists
        if "recorder" in state_copy and state_copy["recorder"]:
            output_file = state_copy["recorder"].output_path
            if file_handler.file_exists(output_file):
                file_handler.delete_file(output_file)


async def upload_to_telegram(client: Client, message: Message, file_path: str, user_id: int):
    """Upload file directly to Telegram."""
    try:
        file_size_mb = file_handler.get_file_size_mb(file_path)
        
        # Check file size
        if file_handler.is_file_too_large(file_path):
            await message.edit_text(
                f"❌ File too large for Telegram!\n\n"
                f"File size: {file_size_mb:.2f} MB\n"
                f"Telegram limit: 4.2 GB\n\n"
                f"Please use GoFile option instead."
            )
            return
        
        await message.edit_text(
            f"📤 Uploading to Telegram...\n"
            f"📁 Size: {file_size_mb:.2f} MB"
        )
        
        # Send file
        await client.send_document(
            chat_id=user_id,
            document=file_path,
            caption="🎬 SONY YAY! SonyLIV Recording\n\n✅ Recording completed successfully!",
            file_name="SONY YAY! SonyLIV Recording.mkv"
        )
        
        await message.edit_text(
            "✅ **Upload Complete!**\n\n"
            "📹 Your SONY YAY! recording has been successfully uploaded to Telegram."
        )
        
    except Exception as e:
        logger.error(f"Telegram upload error for user {user_id}: {e}")
        await message.edit_text(
            f"❌ Upload failed!\n\n"
            f"Error: {str(e)[:100]}"
        )


async def upload_to_gofile(message: Message, file_path: str, user_id: int):
    """Upload file to GoFile."""
    try:
        if not GOFILE_TOKEN:
            await message.edit_text(
                "❌ GoFile upload not configured!\n\n"
                "GOFILE_TOKEN is not set in the bot configuration."
            )
            return
        
        file_size_mb = file_handler.get_file_size_mb(file_path)
        
        await message.edit_text(
            f"📤 Uploading to GoFile...\n"
            f"📁 Size: {file_size_mb:.2f} MB"
        )
        
        success, result = await file_handler.upload_to_gofile(file_path, GOFILE_TOKEN)
        
        if success:
            await message.edit_text(
                f"✅ **Upload Complete!**\n\n"
                f"📁 File size: {file_size_mb:.2f} MB\n"
                f"📥 Download: [GoFile Link]({result})",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.edit_text(
                f"❌ Upload failed!\n\n"
                f"Error: {result}"
            )
    
    except Exception as e:
        logger.error(f"GoFile upload error for user {user_id}: {e}")
        await message.edit_text(
            f"❌ Upload failed!\n\n"
            f"Error: {str(e)[:100]}"
        )


async def set_bot_commands():
    """Set bot commands in Telegram."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("record", "Record SONY YAY stream (HH:MM:SS)"),
        BotCommand("help", "Show help message"),
        BotCommand("about", "About this bot"),
    ]
    await app.set_bot_commands(commands)


async def main():
    """Main function."""
    global file_handler, recording_manager
    
    logger.info("Starting SONY YAY! Recording Bot...")
    
    # Initialize file handler and recording manager
    file_handler, recording_manager = initialize_handlers(RECORDINGS_DIR, MAX_CONCURRENT_RECORDINGS)
    
    if not file_handler or not recording_manager:
        logger.error("Failed to initialize file handler and recording manager")
        sys.exit(1)
    
    # Initialize recording manager semaphore
    await recording_manager.initialize()
    logger.info("File handler and recording manager initialized")
    
    # Start bot
    await app.start()
    logger.info("Bot started successfully!")
    
    # Set bot commands
    try:
        await set_bot_commands()
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")
    
    logger.info(f"Bot is running...")
    logger.info(f"Stream URL: {SONY_STREAM_URL}")
    logger.info(f"Recordings directory: {RECORDINGS_DIR}")
    logger.info(f"Max concurrent recordings: {MAX_CONCURRENT_RECORDINGS}")
    
    await idle()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

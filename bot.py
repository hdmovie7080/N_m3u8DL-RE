"""
SONY YAY! SonyLIV Recording Telegram Bot
Records SONY YAY streams using ffmpeg or N_m3u8DL-RE
"""

import asyncio
import os
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, BotCommand
)
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.enums import ParseMode
from dotenv import load_dotenv

from recording import RecorderFactory
from file_handler import FileHandler, ConcurrentRecordingManager, initialize_handlers

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
GOFILE_TOKEN = os.getenv("GOFILE_TOKEN", "")
SONY_STREAM_URL = os.getenv("SONY_STREAM_URL", "https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "./recordings")
MAX_CONCURRENT_RECORDINGS = int(os.getenv("MAX_CONCURRENT_RECORDINGS", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Validate configuration
if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
    print("ERROR: Missing required environment variables (API_ID, API_HASH, BOT_TOKEN, OWNER_ID)")
    sys.exit(1)

# Setup logging
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

# Global state managers
file_handler: Optional[FileHandler] = None
recording_manager: Optional[ConcurrentRecordingManager] = None
user_states: Dict[int, Dict[str, Any]] = {}


def get_user_state(user_id: int) -> Dict[str, Any]:
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
    """Parse and validate HH:MM:SS format."""
    try:
        parts = duration_str.strip().split(':')
        if len(parts) != 3:
            return None
        
        hours, minutes, seconds = map(int, parts)
        
        if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            return None
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except (ValueError, AttributeError):
        return None


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command."""
    try:
        welcome_text = """🎬 **SONY YAY! Recording Bot**

Welcome! This bot records SONY YAY! SonyLIV streams.

**Quick Start:**
Send `/record HH:MM:SS` to start recording
Example: `/record 01:30:45`

**Commands:**
• `/record HH:MM:SS` - Start recording
• `/help` - Show help
• `/about` - About this bot

**Status:** ✅ Active and Running"""
        await message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"User {message.from_user.id} started the bot")
    except Exception as e:
        logger.error(f"Error in start_command: {e}\n{traceback.format_exc()}")
        try:
            await message.reply_text("❌ Error processing your request.")
        except:
            pass


@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command."""
    try:
        help_text = """📖 **SONY YAY! Recording Bot - Help**

**How to use:**

1. Send `/record HH:MM:SS` to start recording
   Example: `/record 01:30:45`

2. Select your recording method:
   • **FFmpeg** - Fast, direct streaming
   • **N_m3u8DL-RE** - Advanced M3U8 downloader

3. Select delivery method:
   • **Telegram Upload** - Direct to Telegram
   • **GoFile** - Cloud download link

4. Bot will record and upload automatically

**Duration Format:** HH:MM:SS
- HH: Hours (00-23)
- MM: Minutes (00-59)
- SS: Seconds (00-59)"""
        await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in help_command: {e}")


@app.on_message(filters.command("about"))
async def about_command(client: Client, message: Message):
    """Handle /about command."""
    try:
        about_text = """ℹ️ **About SONY YAY! Recording Bot**

**Version:** 1.0.0
**Stream:** SONY YAY! SonyLIV
**Methods:** FFmpeg, N_m3u8DL-RE
**Delivery:** Telegram, GoFile

**Features:**
✅ Dual recording methods
✅ Real-time progress
✅ Multiple delivery options
✅ Concurrent recording support
✅ Auto cleanup

**Status:** ✅ Active and Running"""
        await message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in about_command: {e}")


@app.on_message(filters.command("record"))
async def record_command(client: Client, message: Message):
    """Handle /record HH:MM:SS command."""
    user_id = message.from_user.id
    
    try:
        # Check if user already recording
        if recording_manager.is_user_recording(user_id):
            await message.reply_text("⚠️ You already have an active recording. Wait for it to complete.")
            return
        
        # Parse duration
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text(
                "❌ Invalid format!\n\n`/record HH:MM:SS`\n"
                "Example: `/record 01:30:45`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        duration = parse_duration(args[1])
        if not duration:
            await message.reply_text(
                "❌ Invalid duration format!\n"
                "Use `HH:MM:SS` (e.g., `01:30:45`)",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Check slots
        remaining = recording_manager.get_remaining_slots()
        if remaining <= 0:
            await message.reply_text(
                f"❌ No available slots!\n"
                f"Max concurrent: {recording_manager.max_concurrent}"
            )
            return
        
        # Store state
        state = get_user_state(user_id)
        state["duration"] = duration
        
        # Ask for method
        method_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 FFmpeg", callback_data="method_ffmpeg"),
                InlineKeyboardButton("📥 N_m3u8DL-RE", callback_data="method_n_m3u8dl")
            ]
        ])
        
        msg = await message.reply_text(
            f"📹 **Duration:** `{duration}`\n\n"
            f"Choose recording method:",
            reply_markup=method_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        state["message_id"] = msg.id
        logger.info(f"User {user_id} started recording process with duration {duration}")
        
    except Exception as e:
        logger.error(f"Error in record_command: {e}\n{traceback.format_exc()}")
        try:
            await message.reply_text("❌ Error processing your request.")
        except:
            pass


@app.on_callback_query(filters.regex("^method_"))
async def method_callback(client: Client, callback_query: CallbackQuery):
    """Handle recording method selection."""
    user_id = callback_query.from_user.id
    state = get_user_state(user_id)
    
    try:
        method = callback_query.data.replace("method_", "").upper()
        if method == "N_M3U8DL":
            method = "N_m3u8DL-RE"
        
        state["recording_method"] = method
        
        try:
            await callback_query.message.edit_text(
                f"📹 **Duration:** `{state['duration']}`\n"
                f"**Method:** `{method}`\n\n"
                f"Select delivery method:",
                parse_mode=ParseMode.MARKDOWN
            )
        except MessageNotModified:
            pass
        
        # Ask for delivery
        delivery_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Telegram", callback_data="delivery_telegram")],
            [InlineKeyboardButton("🔗 GoFile", callback_data="delivery_gofile")]
        ])
        
        await callback_query.message.reply_text(
            "How to receive the file?",
            reply_markup=delivery_keyboard
        )
        
        await callback_query.answer()
        logger.info(f"User {user_id} selected method: {method}")
        
    except Exception as e:
        logger.error(f"Error in method_callback: {e}")
        await callback_query.answer("❌ Error processing selection")


@app.on_callback_query(filters.regex("^delivery_"))
async def delivery_callback(client: Client, callback_query: CallbackQuery):
    """Handle delivery method selection."""
    user_id = callback_query.from_user.id
    state = get_user_state(user_id)
    
    try:
        delivery = callback_query.data.replace("delivery_", "").lower()
        state["delivery_method"] = delivery
        
        try:
            await callback_query.message.edit_text(
                f"📹 **Duration:** `{state['duration']}`\n"
                f"**Method:** `{state['recording_method']}`\n"
                f"**Delivery:** `{delivery.upper()}`\n\n"
                f"⏳ Starting recording...",
                parse_mode=ParseMode.MARKDOWN
            )
        except MessageNotModified:
            pass
        
        await callback_query.answer()
        logger.info(f"User {user_id} selected delivery: {delivery}")
        
        # Start recording
        asyncio.create_task(start_recording(client, callback_query.message, user_id, state))
        
    except Exception as e:
        logger.error(f"Error in delivery_callback: {e}")
        await callback_query.answer("❌ Error processing selection")


async def start_recording(client: Client, message: Message, user_id: int, state: dict):
    """Start the actual recording process."""
    try:
        # Acquire slot
        acquired = await recording_manager.acquire(user_id)
        if not acquired:
            await message.reply_text("❌ Failed to acquire recording slot.")
            clear_user_state(user_id)
            return
        
        duration = state["duration"]
        method = state["recording_method"]
        delivery = state["delivery_method"]
        
        # Create output file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{RECORDINGS_DIR}/SONY_YAY_{timestamp}.mkv"
        Path(RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)
        
        # Create recorder
        recorder = RecorderFactory.create(method, SONY_STREAM_URL, duration, output_file)
        state["recorder"] = recorder
        
        # Progress callback
        last_update = [time.time()]
        
        async def progress_callback(progress: dict):
            """Update progress every 5 seconds."""
            now = time.time()
            if now - last_update[0] < 5:
                return
            
            last_update[0] = now
            percent = progress.get("percent", 0)
            elapsed = progress.get("elapsed", "00:00:00")
            total = progress.get("total", duration)
            
            try:
                await message.edit_text(
                    f"📹 **Recording Progress**\n"
                    f"[{'█' * (percent // 10)}{'░' * (10 - percent // 10)}] {percent}%\n"
                    f"⏱️ `{elapsed}` / `{total}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except MessageNotModified:
                pass
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.warning(f"Error updating progress: {e}")
        
        # Run recording
        logger.info(f"Starting recording for user {user_id}: {method}, {duration}")
        success = await recorder.record(progress_callback)
        
        if not success:
            await message.reply_text("❌ Recording failed. Please try again.")
            await recording_manager.release(user_id)
            clear_user_state(user_id)
            if file_handler and file_handler.file_exists(output_file):
                file_handler.delete_file(output_file)
            return
        
        # Upload file
        await message.edit_text("⏳ Processing and uploading file...")
        
        if delivery == "telegram":
            # Upload to Telegram
            try:
                await client.send_document(
                    user_id,
                    output_file,
                    caption=f"📹 **SONY YAY! Recording**\nDuration: `{duration}`\nMethod: `{method}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                await message.reply_text("✅ Recording uploaded to Telegram!")
                logger.info(f"Uploaded recording to Telegram for user {user_id}")
            except Exception as e:
                logger.error(f"Error uploading to Telegram: {e}")
                await message.reply_text(f"❌ Upload failed: {str(e)[:100]}")
        
        elif delivery == "gofile":
            # Upload to GoFile
            if not GOFILE_TOKEN:
                await message.reply_text("❌ GoFile token not configured by admin.")
            else:
                try:
                    success, result = await file_handler.upload_to_gofile(output_file, GOFILE_TOKEN)
                    if success:
                        await message.reply_text(f"✅ Recording uploaded!\n📥 [Download Link]({result})", parse_mode=ParseMode.MARKDOWN)
                        logger.info(f"Uploaded recording to GoFile for user {user_id}")
                    else:
                        await message.reply_text(f"❌ Upload failed: {result}")
                except Exception as e:
                    logger.error(f"Error uploading to GoFile: {e}")
                    await message.reply_text(f"❌ Upload failed: {str(e)[:100]}")
        
        # Cleanup
        await recording_manager.release(user_id)
        if file_handler.file_exists(output_file):
            file_handler.delete_file(output_file)
        clear_user_state(user_id)
        logger.info(f"Recording completed for user {user_id}")
        
    except asyncio.CancelledError:
        logger.info(f"Recording cancelled for user {user_id}")
        await recording_manager.release(user_id)
        clear_user_state(user_id)
    except Exception as e:
        logger.error(f"Error in start_recording: {e}\n{traceback.format_exc()}")
        await recording_manager.release(user_id)
        clear_user_state(user_id)
        try:
            await message.reply_text(f"❌ Unexpected error: {str(e)[:100]}")
        except:
            pass


async def set_bot_commands():
    """Set bot commands."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("record", "Record SONY YAY (HH:MM:SS)"),
        BotCommand("help", "Show help"),
        BotCommand("about", "About this bot"),
    ]
    await app.set_bot_commands(commands)


async def main():
    """Main function."""
    global file_handler, recording_manager
    
    logger.info("=" * 60)
    logger.info("Starting SONY YAY! Recording Bot...")
    logger.info("=" * 60)
    
    # Initialize handlers
    logger.info("Initializing file handler and recording manager...")
    file_handler, recording_manager = initialize_handlers(RECORDINGS_DIR, MAX_CONCURRENT_RECORDINGS)
    await recording_manager.initialize()
    logger.info("✅ Handlers initialized successfully")
    
    # Start bot
    logger.info("Starting Telegram bot...")
    await app.start()
    logger.info("✅ Bot connected to Telegram")
    
    # Set commands
    try:
        await set_bot_commands()
        logger.info("✅ Bot commands configured")
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")
    
    # Log startup info
    logger.info("=" * 60)
    logger.info("✅ BOT IS RUNNING AND READY")
    logger.info("=" * 60)
    logger.info(f"Stream URL: {SONY_STREAM_URL}")
    logger.info(f"Recordings Dir: {RECORDINGS_DIR}")
    logger.info(f"Max Concurrent: {MAX_CONCURRENT_RECORDINGS}")
    logger.info("Waiting for messages...")
    logger.info("=" * 60)
    
    # Keep running
    await idle()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
        sys.exit(1)

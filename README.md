# SONY YAY! Recording Bot

Telegram bot for recording SONY YAY! streams using FFmpeg or N_m3u8DL-RE with Telegram and GoFile upload options.

## Quick Start

### 1. Configure `.env`
Edit `.env` with your Telegram credentials:
```bash
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=your_user_id
GOFILE_TOKEN=your_gofile_token  # Optional
```

### 2. Run with Docker
```bash
docker-compose up -d
```

### 3. Use the Bot
Send `/record HH:MM:SS` to start recording. Example: `/record 01:30:00`

Then select:
- Recording method: **FFmpeg** or **N_m3u8DL-RE**
- Delivery: **Telegram** or **GoFile**

## Files

- `bot.py` - Main Telegram bot application
- `recording.py` - FFmpeg and N_m3u8DL-RE recorders
- `file_handler.py` - File management and uploads
- `.env` - Configuration (edit with your credentials)
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container image
- `docker-compose.yml` - Docker orchestration

## Features

✓ Record SONY YAY streams from fixed URL
✓ Choose recording method (FFmpeg or N_m3u8DL-RE)
✓ Choose delivery method (Telegram or GoFile)
✓ Real-time progress tracking
✓ Concurrent recording management
✓ Automatic file cleanup
✓ Docker ready

## Environment Variables

```env
API_ID=your_api_id                    # From my.telegram.org
API_HASH=your_api_hash                # From my.telegram.org
BOT_TOKEN=your_bot_token              # From @BotFather
OWNER_ID=your_user_id                 # From @userinfobot
SONY_STREAM_URL=https://...           # Stream URL (default provided)
GOFILE_TOKEN=your_gofile_token        # Optional for GoFile uploads
RECORDINGS_DIR=./recordings           # Local recordings folder
MAX_CONCURRENT_RECORDINGS=3           # Max simultaneous recordings
MAX_FILE_SIZE_MB=4096                 # Max file size
LOG_LEVEL=INFO                        # Logging level
```

## Commands

- `/start` - Start the bot and show welcome message
- `/record HH:MM:SS` - Start recording with specified duration
- `/cancel` - Cancel active recording
- `/status` - Show recording status and available slots
- `/help` - Show help message

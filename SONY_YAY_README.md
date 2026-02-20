# 🎬 SONY YAY! SonyLIV Recording Bot

A powerful Telegram bot for recording SONY YAY! SonyLIV streams with dual recording methods and flexible delivery options.

## ✨ Features

- **🎬 Dual Recording Methods:**
  - FFmpeg: Direct stream recording (faster)
  - N_m3u8DL-RE: Advanced M3U8 downloader

- **📤 Multiple Delivery Options:**
  - Direct Telegram upload (up to 4.2GB)
  - GoFile cloud link sharing

- **⚡ Advanced Capabilities:**
  - Real-time progress updates
  - Concurrent recording support (configurable)
  - Automatic file cleanup
  - Duration validation (HH:MM:SS format)
  - Robust error handling

## 📋 Requirements

- Python 3.8+
- FFmpeg (system package)
- N_m3u8DL-RE (installed via Docker or manually)
- Pyrogram & dependencies
- MongoDB (optional, removed in new version)

## 🔧 Installation

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/hdmovie7080/N_m3u8DL-RE.git
cd N_m3u8DL-RE
```

2. Configure `.env`:
```bash
# Required
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=your_owner_id

# SONY Stream
SONY_STREAM_URL=https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8
GOFILE_TOKEN=your_gofile_token (optional)

# Optional
RECORDINGS_DIR=./recordings
MAX_CONCURRENT_RECORDINGS=3
LOG_LEVEL=INFO
```

3. Build and run:
```bash
docker-compose up -d
```

### Manual Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install FFmpeg:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

3. Install N_m3u8DL-RE:
```bash
# Linux
wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0-beta/N_m3u8DL-RE_linux_x64
chmod +x N_m3u8DL-RE_linux_x64
sudo mv N_m3u8DL-RE_linux_x64 /usr/local/bin/N_m3u8DL-RE

# Or use your package manager
```

4. Configure `.env` as shown above

5. Run the bot:
```bash
python bot.py
```

## 🚀 Usage

### Basic Commands

- **`/start`** - Start the bot and show welcome message
- **`/help`** - Show detailed help information
- **`/about`** - View bot information and status
- **`/record HH:MM:SS`** - Start recording

### Recording Examples

```
/record 01:30:45    # Record for 1 hour 30 minutes 45 seconds
/record 00:15:00    # Record for 15 minutes
/record 02:00:00    # Record for 2 hours
```

### Recording Process

1. Send `/record HH:MM:SS` command
2. Choose recording method:
   - **FFmpeg** - Recommended for stability
   - **N_m3u8DL-RE** - Better for complex streams
3. Choose delivery method:
   - **Telegram Upload** - Direct file upload (faster)
   - **GoFile Link** - Cloud link sharing
4. Bot starts recording with progress updates
5. Upon completion, file is uploaded automatically

## 📁 Project Structure

```
.
├── bot.py                    # Main bot application
├── recording.py              # Recording engines (FFmpeg & N_m3u8DL-RE)
├── file_handler.py           # File management & uploads
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker configuration
├── docker-compose.yml        # Docker Compose setup
├── .env                      # Environment variables
└── SONY_YAY_README.md        # This file
```

## 🏗️ Architecture

### Bot Core (`bot.py`)
- Telegram command handlers (`/start`, `/record`, `/help`, `/about`)
- Callback query handlers for method/delivery selection
- Progress update mechanisms
- File upload orchestration

### Recording Module (`recording.py`)
- `RecorderBase`: Abstract recorder class
- `FFmpegRecorder`: FFmpeg-based implementation
- `N_m3u8DLRecorder`: N_m3u8DL-RE wrapper
- `RecorderFactory`: Factory pattern for recorder creation
- Duration parsing and validation
- Progress tracking

### File Handler (`file_handler.py`)
- `FileHandler`: Local file management
  - File size checks
  - GoFile API integration
  - Automatic cleanup
- `ConcurrentRecordingManager`: Manage concurrent recordings
  - Semaphore-based slot management
  - User state tracking

## 🔐 Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_ID` | Yes | - | Telegram API ID |
| `API_HASH` | Yes | - | Telegram API Hash |
| `BOT_TOKEN` | Yes | - | Telegram Bot Token |
| `OWNER_ID` | Yes | - | Bot Owner's User ID |
| `SONY_STREAM_URL` | No | SONY URL | Stream M3U8 URL |
| `GOFILE_TOKEN` | No | - | GoFile API token |
| `RECORDINGS_DIR` | No | `./recordings` | Local recording directory |
| `MAX_CONCURRENT_RECORDINGS` | No | `3` | Max simultaneous recordings |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## 🐛 Troubleshooting

### FFmpeg Not Found
```bash
# Check if FFmpeg is installed
ffmpeg -version

# If not installed:
sudo apt-get install ffmpeg
```

### N_m3u8DL-RE Not Found
```bash
# Check installation
N_m3u8DL-RE --help

# Reinstall if needed
wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0-beta/N_m3u8DL-RE_linux_x64
chmod +x N_m3u8DL-RE_linux_x64
sudo mv N_m3u8DL-RE_linux_x64 /usr/local/bin/N_m3u8DL-RE
```

### Permission Denied on Docker
```bash
# Fix permission issues
sudo usermod -aG docker $USER
newgrp docker
docker-compose up -d
```

### File Upload Failures

**Telegram Upload Too Large:**
- Use GoFile option for files > 4GB
- Split longer recordings

**GoFile Upload Issues:**
- Verify `GOFILE_TOKEN` in `.env`
- Check internet connection
- GoFile may be down

### Recording Quality Issues

1. **Check stream availability:**
```bash
curl -I https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8
```

2. **Try different recording method:**
   - Switch between FFmpeg and N_m3u8DL-RE
   - Each has different compatibility

3. **Check logs:**
```bash
tail -f sony_bot.log
```

## 📊 Logging

Bot logs are saved to `sony_bot.log`:

```bash
# View recent logs
tail -f sony_bot.log

# View error logs
grep ERROR sony_bot.log

# View specific user logs
grep "user_id" sony_bot.log
```

## 🔄 Docker Commands

```bash
# Start bot
docker-compose up -d

# Stop bot
docker-compose down

# View logs
docker-compose logs -f sony-yay-bot

# Rebuild after code changes
docker-compose up -d --build

# Remove volumes (WARNING: deletes recordings)
docker-compose down -v
```

## 💡 Tips & Best Practices

1. **Recording Duration:**
   - Keep recordings under 2 hours for stability
   - Longer recordings = larger files = slower uploads

2. **Concurrent Recordings:**
   - Default is 3 simultaneous recordings
   - Adjust based on server resources
   - Each recording uses significant bandwidth

3. **File Management:**
   - Recordings auto-cleanup after successful upload
   - Failed recordings remain in directory
   - Manually delete if needed: `rm recordings/*`

4. **Method Selection:**
   - **FFmpeg**: Better for stable streams
   - **N_m3u8DL-RE**: Better for complex/fragmented streams

5. **Delivery Selection:**
   - **Telegram**: Convenient, up to 4.2GB
   - **GoFile**: For large files, longer retention

## 🆘 Getting Help

1. **Check Logs:**
   ```bash
   tail -f sony_bot.log
   ```

2. **Verify Configuration:**
   - Ensure all required env vars are set
   - Check FFmpeg and N_m3u8DL-RE installation

3. **Test Manually:**
   ```bash
   # Test FFmpeg
   ffmpeg -i https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8 -t 00:01:00 -c copy test.mkv
   
   # Test N_m3u8DL-RE
   N_m3u8DL-RE https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8 -max-time 00:01:00
   ```

## 📝 License

This project is based on N_m3u8DL-RE repository.

## ⚠️ Disclaimer

This bot is for personal use only. Respect copyright and streaming service terms of service. The developer is not responsible for misuse.

## 🤝 Contributing

Feel free to submit issues and pull requests!

---

**Version:** 1.0.0  
**Last Updated:** 2026-02-20  
**Status:** Active ✅

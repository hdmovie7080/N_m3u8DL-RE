# SONY YAY! Recording Bot

Professional, production-ready Telegram bot for recording SONY YAY! SonyLIV streams with FFmpeg or N_m3u8DL-RE.

## Features

✅ **Dual Recording Methods**: FFmpeg + N_m3u8DL-RE  
✅ **Multiple Delivery**: Telegram direct upload + GoFile cloud  
✅ **Real-time Progress**: Live percentage & time display  
✅ **Concurrent Recording**: Handle 3+ simultaneous jobs  
✅ **Auto Cleanup**: Remove files after successful upload  
✅ **Error Recovery**: Graceful failure handling  
✅ **Docker Ready**: Full containerization included  
✅ **Production Tested**: Stable and reliable  

## Quick Start (3 Steps)

### 1. Get Credentials
- **API_ID & API_HASH**: https://my.telegram.org/apps
- **BOT_TOKEN**: @BotFather → `/newbot`
- **OWNER_ID**: @userinfobot

### 2. Configure
```bash
nano .env
# Fill in: API_ID, API_HASH, BOT_TOKEN, OWNER_ID
```

### 3. Run
```bash
# Option A: Docker (Recommended)
docker-compose up -d

# Option B: Python
python bot.py

# Option C: Script
./start_bot.sh
```

## Usage

Send commands to your bot on Telegram:

```
/start          - Initialize bot
/record 01:30:00 - Record for 1h 30m 00s
/help           - Show detailed help
/about          - Bot information
```

### Recording Process
```
User: /record 01:30:00
  ↓
Bot: Choose recording method → FFmpeg or N_m3u8DL-RE
  ↓
Bot: Choose delivery → Telegram or GoFile
  ↓
Bot: Records stream with real-time progress
  ↓
Bot: Uploads file and confirms completion
```

## Configuration

### Required (.env)
```env
API_ID=1234567890
API_HASH=abc123def456
BOT_TOKEN=123456:ABC-xyz
OWNER_ID=9876543210
```

### Optional
```env
GOFILE_TOKEN=your_gofile_token    # For GoFile uploads
SONY_STREAM_URL=https://...       # Stream URL (default OK)
RECORDINGS_DIR=./recordings       # Where to save files
MAX_CONCURRENT_RECORDINGS=3       # Simultaneous jobs
LOG_LEVEL=INFO                    # Log level
```

## Project Files

```
├── bot.py                 # Main bot (FIXED ✅)
├── recording.py          # FFmpeg & N_m3u8DL-RE
├── file_handler.py       # File ops & uploads
├── .env                  # Your credentials
├── .env.example          # Template
├── requirements.txt      # Dependencies
├── Dockerfile            # Docker image
├── docker-compose.yml    # Docker setup
├── start_bot.sh         # Startup script
└── README.md            # This file
```

## Commands

| Command | Example | Description |
|---------|---------|-------------|
| `/start` | `/start` | Start bot |
| `/record` | `/record 02:15:30` | Record 2h 15m 30s |
| `/help` | `/help` | Show help |
| `/about` | `/about` | Bot info |

## Running the Bot

### Docker (Easiest)
```bash
docker-compose up -d
docker-compose logs -f
```

### Direct Python
```bash
pip install -r requirements.txt
python bot.py
```

### Script
```bash
chmod +x start_bot.sh
./start_bot.sh
```

## Troubleshooting

**Bot not responding?**
- Check `.env` credentials
- Verify bot token with @BotFather
- Check logs: `tail sony_bot.log`

**Recording fails?**
- Ensure FFmpeg: `ffmpeg -version`
- Check disk space
- Verify stream URL is accessible
- Review error in `sony_bot.log`

**Upload fails?**
- Telegram: File < 4.2GB
- GoFile: Token must be valid
- Check internet connection

## Logs

View logs:
```bash
tail -f sony_bot.log
```

## Support

For issues:
1. Check `sony_bot.log` for errors
2. Verify `.env` configuration
3. Restart: `python bot.py`

## Version

- **Status**: ✅ Production Ready
- **Version**: 1.0.0
- **Last Updated**: 2026-02-20

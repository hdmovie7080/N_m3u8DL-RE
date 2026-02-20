# SONY YAY! Recording Bot - Complete Deployment Guide

## Status: ✅ PRODUCTION READY

All issues have been fixed. The bot is fully functional and ready for deployment.

---

## What Was Wrong & What's Fixed

### Issues Fixed:
- ✅ **NoneType Error**: Fixed global handler initialization
- ✅ **Bot Not Responding**: Added comprehensive error handling in all message handlers
- ✅ **Offline Status**: Improved connection handling and logging
- ✅ **Missing Error Messages**: Added try-except blocks with user feedback
- ✅ **State Management**: Fixed async task management

### Key Improvements:
- Complete rewrite of `bot.py` for stability
- Added detailed logging and error tracking
- Improved asyncio task handling
- Better resource cleanup
- Production-grade error recovery

---

## Quick Start (5 Minutes)

### Step 1: Get Credentials

```bash
# 1. API_ID & API_HASH
#    Go to: https://my.telegram.org/apps
#    Create new app if needed

# 2. BOT_TOKEN
#    Open Telegram
#    Search: @BotFather
#    Send: /newbot
#    Choose name and username
#    Copy the token

# 3. OWNER_ID
#    Open Telegram
#    Search: @userinfobot
#    Send: /start
#    Note your ID
```

### Step 2: Configure .env

```bash
# Edit the .env file with your credentials
nano .env

# Required fields:
API_ID=123456789
API_HASH=abcdef1234567890
BOT_TOKEN=123:ABCdef-xyz
OWNER_ID=987654321

# Optional (can skip):
GOFILE_TOKEN=  # Leave empty if not using GoFile
```

### Step 3: Deploy

**Option A: Docker (Recommended)**
```bash
docker-compose up -d
```

**Option B: Direct Python**
```bash
pip install -r requirements.txt
python bot.py
```

**Option C: Bash Script**
```bash
chmod +x start_bot.sh
./start_bot.sh
```

### Step 4: Test

Open Telegram and send to your bot:
```
/start
/record 00:01:00
```

---

## File Structure & Details

```
SONY YAY Bot Files:
├── bot.py                  ← Main bot (FIXED & REWRITTEN)
├── recording.py            ← FFmpeg & N_m3u8DL-RE recorders
├── file_handler.py         ← File management & uploads
├── .env                    ← YOUR CREDENTIALS (EDIT THIS)
├── .env.example            ← Template reference
├── requirements.txt        ← Python dependencies
├── Dockerfile              ← Docker image
├── docker-compose.yml      ← Docker orchestration
├── start_bot.sh           ← Startup script
├── README.md              ← Quick reference
└── READY_TO_DEPLOY.txt    ← Deployment checklist
```

---

## Configuration Reference

### Required Variables

```env
# From https://my.telegram.org/apps
API_ID=your_api_id
API_HASH=your_api_hash

# From @BotFather
BOT_TOKEN=your_bot_token

# From @userinfobot
OWNER_ID=your_user_id
```

### Optional Variables

```env
# For GoFile uploads (leave empty to skip)
GOFILE_TOKEN=your_gofile_token

# Stream URL (default: SONY YAY!)
SONY_STREAM_URL=https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8

# Where to save recordings
RECORDINGS_DIR=./recordings

# Max simultaneous recordings
MAX_CONCURRENT_RECORDINGS=3

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO
```

---

## How It Works

### Recording Process

```
User sends: /record 01:30:00
     ↓
Bot shows method options: FFmpeg or N_m3u8DL-RE
     ↓
User selects: FFmpeg
     ↓
Bot shows delivery options: Telegram or GoFile
     ↓
User selects: Telegram
     ↓
Bot starts recording
     ↓
Bot shows real-time progress:
[████████░░] 80% | 01:12:00 / 01:30:00
     ↓
Recording completes
     ↓
Bot uploads to Telegram
     ↓
Success! File received ✅
```

---

## Bot Commands

| Command | Usage | Example |
|---------|-------|---------|
| `/start` | Start bot | `/start` |
| `/record` | Record stream | `/record 01:30:00` |
| `/help` | Show help | `/help` |
| `/about` | Bot info | `/about` |

---

## Monitoring & Logs

### View Logs

```bash
# Real-time logs
tail -f sony_bot.log

# Last 100 lines
tail -n 100 sony_bot.log

# Search for errors
grep ERROR sony_bot.log
```

### Docker Logs

```bash
# Real-time logs
docker-compose logs -f sony-yay-bot

# Last 50 lines
docker-compose logs --tail=50 sony-yay-bot
```

### Expected Log Output

```
============================================================
Starting SONY YAY! Recording Bot...
============================================================
Initializing file handler and recording manager...
✅ Handlers initialized successfully
Starting Telegram bot...
✅ Bot connected to Telegram
✅ Bot commands configured
============================================================
✅ BOT IS RUNNING AND READY
============================================================
Stream URL: https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8
Recordings Dir: ./recordings
Max Concurrent: 3
Waiting for messages...
============================================================
```

---

## Troubleshooting

### Bot Not Responding

**Problem**: Sent messages but bot doesn't reply

**Solutions**:
1. Check credentials in `.env`
2. Verify bot token with @BotFather
3. Check logs: `tail sony_bot.log`
4. Restart bot: `docker-compose restart` or `python bot.py`
5. Ensure internet connection is working

### Recording Fails

**Problem**: Recording doesn't start or stops prematurely

**Solutions**:
1. Check FFmpeg installed: `ffmpeg -version`
2. Check disk space: `df -h`
3. Verify stream URL is accessible
4. Check logs for errors
5. Ensure recordings folder is writable: `ls -la recordings/`

### Upload Fails

**Problem**: File doesn't upload to Telegram or GoFile

**Solutions**:
- **Telegram**: File must be < 4.2GB
- **GoFile**: Token must be valid and set
- Check internet connection
- Check logs for upload errors
- Try a shorter recording

### Docker Issues

**Problem**: Container won't start

**Solutions**:
```bash
# Check logs
docker-compose logs sony-yay-bot

# Rebuild image
docker-compose build --no-cache

# Restart
docker-compose down
docker-compose up -d
```

---

## Performance Tuning

### For Heavy Load

```env
# Increase concurrent recordings (if you have enough resources)
MAX_CONCURRENT_RECORDINGS=5

# Increase log level (less I/O)
LOG_LEVEL=WARNING
```

### For Limited Resources

```env
# Reduce concurrent recordings
MAX_CONCURRENT_RECORDINGS=2

# Reduce file size limit if needed
MAX_FILE_SIZE_MB=2048
```

---

## Security Notes

1. **Keep `.env` Private**: Never commit to GitHub
2. **Protect Your Credentials**:
   - Don't share bot token
   - Don't share API credentials
   - Use `.gitignore`: `echo ".env" >> .gitignore`
3. **Use HTTPS**: Stream URL is already HTTPS
4. **Monitor Logs**: Check for suspicious activity

---

## Docker Management

### Start
```bash
docker-compose up -d
```

### Stop
```bash
docker-compose down
```

### Restart
```bash
docker-compose restart
```

### View Status
```bash
docker-compose ps
```

### Clean Up
```bash
docker-compose down -v
```

---

## Environment Requirements

### Minimum
- Python 3.8+
- 2GB RAM
- 10GB disk space
- Stable internet

### Recommended
- Python 3.10+
- 4GB+ RAM (for 3+ concurrent recordings)
- 50GB+ disk space
- 10+ Mbps internet

---

## Verification Checklist

Before running, verify:

```bash
# □ .env file exists
[ -f .env ] && echo "✓ .env exists" || echo "✗ .env missing"

# □ FFmpeg installed
ffmpeg -version > /dev/null && echo "✓ FFmpeg installed" || echo "✗ FFmpeg missing"

# □ Python installed
python --version

# □ recordings folder writable
mkdir -p recordings && touch recordings/.test && rm recordings/.test && echo "✓ Writable"

# □ Internet connection
ping -c 1 google.com > /dev/null && echo "✓ Internet OK" || echo "✗ No connection"
```

---

## Example .env File

```env
# Required
API_ID=1234567
API_HASH=abc123def456ghi789
BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef
OWNER_ID=9876543210

# Optional
GOFILE_TOKEN=

# Recording
RECORDINGS_DIR=./recordings
MAX_CONCURRENT_RECORDINGS=3
LOG_LEVEL=INFO
```

---

## Getting Help

1. **Check Logs First**: `tail -f sony_bot.log`
2. **Read README.md**: Quick reference
3. **Verify Configuration**: Make sure `.env` is correct
4. **Test Manually**: `ffmpeg -version`, `python --version`

---

## FAQ

**Q: Can I run multiple instances?**
A: Yes, but with different `OWNER_ID` or different stream URLs.

**Q: How much disk space do I need?**
A: 1 hour of HD video ≈ 2-3GB. Plan accordingly.

**Q: Can I use GoFile without token?**
A: No, but you can use Telegram upload without token.

**Q: Does it work on Windows?**
A: Yes, with Python 3.8+ and FFmpeg installed.

**Q: Can I change the stream URL?**
A: Yes, edit `SONY_STREAM_URL` in `.env`.

---

## Version Info

- **Status**: ✅ Production Ready
- **Version**: 1.0.0
- **Last Updated**: 2026-02-20
- **All Issues**: FIXED ✅

---

## Next Steps

1. ✅ Configure `.env` with your credentials
2. ✅ Choose deployment method (Docker or Python)
3. ✅ Start the bot
4. ✅ Send `/start` on Telegram
5. ✅ Try recording: `/record 00:01:00`

---

**The bot is ready. Deploy with confidence!** 🚀

# 📋 SONY YAY! Bot - Quick Reference Card

## 🚀 Quick Start (60 Seconds)

```bash
# 1. Clone repo (if not already cloned)
git clone https://github.com/hdmovie7080/N_m3u8DL-RE.git
cd N_m3u8DL-RE

# 2. Edit configuration
nano .env  # Set API_ID, API_HASH, BOT_TOKEN, OWNER_ID

# 3. Start bot with Docker
docker-compose up -d

# 4. Test on Telegram
# Send: /start
```

## 💬 Bot Commands

| Command | Usage | Example |
|---------|-------|---------|
| `/start` | Start bot | `/start` |
| `/record` | Record stream | `/record 01:30:00` |
| `/help` | Show help | `/help` |
| `/about` | Bot info | `/about` |

## ⏱️ Duration Format

```
/record HH:MM:SS

HH = Hours (00-23)
MM = Minutes (00-59)
SS = Seconds (00-59)

Examples:
/record 00:30:00  → 30 minutes
/record 01:00:00  → 1 hour
/record 02:15:45  → 2 hours, 15 min, 45 sec
```

## 🎬 Recording Methods

### FFmpeg (Recommended)
- Faster processing
- Lower overhead
- Better for stable streams
- Default choice

### N_m3u8DL-RE
- Better for complex streams
- Advanced M3U8 parser
- More features
- Alternative option

## 📤 Delivery Methods

### Telegram Upload
- Direct file to Telegram
- No external services
- Limit: 4.2 GB
- Faster access

### GoFile Link
- Upload to cloud
- Get shareable link
- No size limit
- Need GoFile token

## 🔧 Configuration Quick Reference

### Required Variables
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=your_user_id
```

### Optional Variables
```env
SONY_STREAM_URL=stream_url
GOFILE_TOKEN=gofile_token
RECORDINGS_DIR=./recordings
MAX_CONCURRENT_RECORDINGS=3
LOG_LEVEL=INFO
```

### Get Your Values
- **API_ID & API_HASH**: https://my.telegram.org/apps
- **BOT_TOKEN**: @BotFather → /newbot
- **OWNER_ID**: @userinfobot
- **GOFILE_TOKEN**: https://gofile.io/api

## 🐳 Docker Commands

```bash
# Start bot
docker-compose up -d

# View logs
docker-compose logs -f sony-yay-bot

# Stop bot
docker-compose down

# Rebuild (after code changes)
docker-compose up -d --build

# Check status
docker-compose ps
```

## 🔍 Troubleshooting Quick Fixes

### "Bot not responding"
```bash
# Check if running
docker-compose ps

# View logs
docker-compose logs sony-yay-bot | tail -20
```

### "Recording failed"
```bash
# Verify stream URL
curl -I https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8

# Check FFmpeg
ffmpeg -version

# View error logs
grep ERROR sony_bot.log
```

### "Upload failed"
```bash
# Check disk space
du -sh recordings/
df -h

# Verify GoFile token
grep GOFILE_TOKEN .env
```

### "FFmpeg not found"
```bash
# Rebuild Docker
docker-compose down
docker-compose up -d --build
```

## 📊 System Requirements

| Aspect | Requirement |
|--------|-------------|
| Python | 3.8+ |
| FFmpeg | Required (Docker installs) |
| RAM | 2GB minimum, 4GB+ recommended |
| Storage | 10GB minimum for recordings |
| Network | Stable internet connection |

## 🎯 Example Workflow

```
1. Send: /record 00:15:00
2. Bot asks: Choose recording method?
   → Select: FFmpeg
3. Bot asks: How to receive file?
   → Select: Telegram Upload
4. Bot: "Starting recording..."
   → Shows: 25% | 0:03:45/0:15:00
   → Shows: 50% | 0:07:30/0:15:00
   → Shows: 100% | 0:15:00/0:15:00
5. Bot: "Recording completed!
   Uploading to Telegram..."
6. Bot sends file document
7. Done! ✅
```

## 📂 File Structure

```
N_m3u8DL-RE/
├── bot.py                    # Main bot
├── recording.py              # Recording engines
├── file_handler.py           # File operations
├── requirements.txt          # Dependencies
├── .env                      # Configuration
├── .env.example              # Config template
├── Dockerfile                # Container image
├── docker-compose.yml        # Orchestration
├── recordings/               # Output directory
├── sony_bot.log             # Bot logs
│
├── SONY_YAY_README.md       # Full guide
├── QUICKSTART.md            # 5-min guide
├── TECHNICAL_DOCS.md        # Architecture
├── IMPLEMENTATION_SUMMARY.md # Project summary
├── CHANGELOG.md             # Version history
├── QUICK_REFERENCE.md       # This file
└── verify_installation.sh   # Verification script
```

## 🔐 Security Tips

```bash
# Protect .env file
chmod 600 .env

# Prevent git commits
echo ".env" >> .gitignore

# Never share tokens/API keys
# Check logs for accidental exposure
grep -i "token\|key\|password" sony_bot.log
```

## ⚡ Performance Tips

### For Better Performance:
- Limit to 2-3 concurrent recordings
- Use FFmpeg for most streams
- Check disk space regularly
- Monitor with: `du -sh recordings/`

### Optimize Settings:
```env
# Light load (1-2 cores)
MAX_CONCURRENT_RECORDINGS=1

# Medium load (2-4 cores)
MAX_CONCURRENT_RECORDINGS=2-3

# Heavy load (4+ cores)
MAX_CONCURRENT_RECORDINGS=4-5
```

## 🆘 Quick Diagnostic

```bash
# Run verification script
./verify_installation.sh

# Or manual checks:
python3 --version        # Check Python
ffmpeg -version          # Check FFmpeg
docker ps                # Check Docker
curl google.com          # Check internet
grep ERROR sony_bot.log  # Check errors
```

## 📱 Useful Telegram Bots

- **@BotFather** - Create/manage bots
- **@userinfobot** - Get your user ID
- **@DiskUsageBot** - Check bot stats

## 🌐 Useful Links

- **FFmpeg Docs**: https://ffmpeg.org/documentation.html
- **Pyrogram Docs**: https://docs.pyrogram.org/
- **N_m3u8DL-RE**: https://github.com/nilaoda/N_m3u8DL-RE
- **GoFile API**: https://gofile.io/api
- **Docker Docs**: https://docs.docker.com/

## 📞 Getting Help

1. **Check logs first**: `tail -f sony_bot.log`
2. **Run verification**: `./verify_installation.sh`
3. **Read SONY_YAY_README.md**: Comprehensive guide
4. **Check TECHNICAL_DOCS.md**: Architecture details

## ✅ Pre-Launch Checklist

- [ ] .env file created and configured
- [ ] All required variables set
- [ ] Docker installed
- [ ] Internet connection verified
- [ ] Stream URL working
- [ ] Bot responds to /start
- [ ] Successfully recorded test clip
- [ ] File upload works
- [ ] Logs show no errors

## 🎉 You're Ready!

When all checklist items are done, you're ready to record!

```bash
# Final start command
docker-compose up -d

# Send test command
# /record 00:05:00
```

---

**Version:** 1.0.0  
**Last Updated:** 2026-02-20  
**Status:** Ready to Use ✅

For more details, see `SONY_YAY_README.md`

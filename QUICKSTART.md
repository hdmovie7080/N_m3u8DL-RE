# ⚡ Quick Start Guide - SONY YAY! Recording Bot

## 5-Minute Setup

### Step 1: Prerequisites ✅
- Docker & Docker Compose installed
- Telegram Bot Token (from @BotFather)
- Your Telegram API ID and Hash (from https://my.telegram.org)
- Your User ID (from @userinfobot)

### Step 2: Clone & Configure 🔧

```bash
# Clone repository
git clone https://github.com/hdmovie7080/N_m3u8DL-RE.git
cd N_m3u8DL-RE

# Edit .env file
nano .env  # or use your favorite editor
```

**Minimal .env Configuration:**
```env
# Telegram (REQUIRED)
API_ID=123456789
API_HASH=abcd1234efgh5678ijkl9012mnop3456
BOT_TOKEN=9876543210:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef123
OWNER_ID=1234567890

# Stream (Optional - uses default SONY URL)
SONY_STREAM_URL=https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8
GOFILE_TOKEN=your_gofile_token_here

# Defaults - Don't change unless needed
RECORDINGS_DIR=./recordings
MAX_CONCURRENT_RECORDINGS=3
```

### Step 3: Run Bot 🚀

```bash
# Start with Docker
docker-compose up -d

# Check if running
docker-compose logs -f sony-yay-bot

# You should see: "Bot started successfully!"
```

### Step 4: Test Bot 📱

1. Open Telegram
2. Search for your bot (by username)
3. Send `/start` command
4. Bot should reply with welcome message

### Step 5: Record Your First Stream 🎥

1. Send to bot: `/record 00:30:00`
2. Choose recording method:
   - ✅ **FFmpeg** (recommended for most cases)
3. Choose delivery:
   - ✅ **Telegram Upload** (if file < 4GB)
   - 🔗 **GoFile Link** (if you need cloud storage)
4. Wait for recording to complete
5. File will be automatically uploaded!

---

## Common Issues & Solutions

### "Bot Token Invalid"
```bash
# Check your BOT_TOKEN in .env
# Make sure it's correct from @BotFather
# Restart: docker-compose restart sony-yay-bot
```

### "FFmpeg not found"
```bash
# Rebuild Docker image
docker-compose down
docker-compose up -d --build
```

### "Recording didn't start"
```bash
# Check logs
docker-compose logs sony-yay-bot | tail -20

# Verify SONY_STREAM_URL is accessible
curl -I https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8
```

### "File upload failed"
- For **Telegram**: Check if file > 4GB → use GoFile instead
- For **GoFile**: Verify GOFILE_TOKEN is set correctly

---

## 📊 Monitor Bot

```bash
# View live logs
docker-compose logs -f sony-yay-bot

# Check disk usage
du -sh ./recordings

# Stop bot
docker-compose down

# Start bot again
docker-compose up -d
```

---

## 🎯 Example Recordings

**Short Clip:**
```
/record 00:15:00   # 15-minute recording
```

**Standard Episode:**
```
/record 00:45:00   # 45-minute recording
```

**Full Session:**
```
/record 02:00:00   # 2-hour recording
```

---

## 🔐 Security Tips

1. **Keep tokens private:**
   - Never share `.env` file
   - Never commit `.env` to GitHub
   - `.env` is in `.gitignore` for a reason

2. **Limit access:**
   - Only you should be able to message the bot
   - For multi-user, implement permission checks

3. **Monitor logs:**
   - Regularly check bot logs for errors
   - Watch for unauthorized access attempts

---

## 📱 Bot Commands

| Command | Usage | Example |
|---------|-------|---------|
| `/start` | Initialize bot | `/start` |
| `/record` | Start recording | `/record 01:30:45` |
| `/help` | Show help | `/help` |
| `/about` | Bot info | `/about` |

---

## 🆘 Need Help?

1. **Check logs first:**
   ```bash
   docker-compose logs sony-yay-bot
   ```

2. **Verify configuration:**
   ```bash
   cat .env
   ```

3. **Test components:**
   ```bash
   # Test FFmpeg
   ffmpeg -version
   
   # Test N_m3u8DL-RE
   N_m3u8DL-RE --help
   ```

4. **Check the main README:**
   - See `SONY_YAY_README.md` for detailed documentation

---

## 🎉 You're Ready!

Your SONY YAY! Recording Bot is now running. Start recording streams!

**Happy Recording!** 🎬✨

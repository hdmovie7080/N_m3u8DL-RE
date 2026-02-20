# 🏗️ SONY YAY! Bot - Technical Documentation

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram User                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Main Bot (bot.py)                           │
│  - Command Handlers (/record, /start, /help, /about)            │
│  - Callback Handlers (method & delivery selection)              │
│  - Message Routing & State Management                           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
        ┌─────────────────┐        ┌─────────────────┐
        │  Recording      │        │  File Handler   │
        │  Module         │        │  Module         │
        │ (recording.py)  │        │ (file_handler.py)
        └─────────────────┘        └─────────────────┘
                │                             │
    ┌───────────┴───────────┐       ┌────────┴────────┐
    ▼                       ▼       ▼                  ▼
┌─────────┐         ┌──────────┐  ┌────────┐   ┌──────────┐
│ FFmpeg  │         │N_m3u8DL- │  │Telegram│   │  GoFile  │
│ Process │         │RE Process│  │ Upload │   │  Upload  │
└─────────┘         └──────────┘  └────────┘   └──────────┘
    │                     │            │           │
    └─────────────────────┴────────────┴───────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Recording  │
                    │   Files     │
                    │ (recordings/│
                    │  directory) │
                    └─────────────┘
```

## Module Breakdown

### 1. bot.py (Main Application)

**Core Responsibilities:**
- Telegram bot initialization and connection
- Command and callback query handling
- User state management
- Recording orchestration
- Progress updates

**Key Classes/Functions:**

```python
# State management
get_user_state(user_id: int) -> dict
clear_user_state(user_id: int) -> None
parse_duration(duration_str: str) -> Optional[str]

# Command handlers
@app.on_message(filters.command("start"))
@app.on_message(filters.command("record"))
@app.on_message(filters.command("help"))
@app.on_message(filters.command("about"))

# Callback handlers
@app.on_callback_query(filters.regex("^method_"))
@app.on_callback_query(filters.regex("^delivery_"))

# Recording management
start_recording(client, message, user_id, state) -> None
upload_to_telegram(client, message, file_path, user_id) -> None
upload_to_gofile(message, file_path, user_id) -> None
```

**User State Structure:**
```python
user_states = {
    user_id: {
        "recording_method": "FFmpeg" | "N_m3u8DL-RE",
        "delivery_method": "telegram" | "gofile",
        "duration": "HH:MM:SS",
        "message_id": int,
        "recording_task": asyncio.Task,
        "recorder": RecorderBase instance
    }
}
```

### 2. recording.py (Recording Engines)

**Core Responsibilities:**
- Implement recording methods
- Handle process lifecycle
- Progress tracking
- Error handling and cancellation

**Class Hierarchy:**

```
RecorderBase (Abstract)
├── FFmpegRecorder
├── N_m3u8DLRecorder
└── RecorderFactory (Factory Pattern)
```

**RecorderBase Methods:**
```python
def parse_duration(self) -> int:
    """Convert HH:MM:SS to seconds"""

def get_progress(self) -> Dict[str, Any]:
    """Return current progress (percent, elapsed, etc)"""

async def cancel(self):
    """Cancel recording gracefully"""

async def record(self, progress_callback) -> bool:
    """Start recording (overridden by subclasses)"""
```

**FFmpeg Recording Command:**
```bash
ffmpeg -nostdin \
  -rw_timeout 15000000 \
  -i <STREAM_URL> \
  -map p:7 \
  -map_metadata 0 \
  -map -0:d \
  -c copy \
  -t <DURATION> \
  -y <OUTPUT_FILE>
```

**N_m3u8DL-RE Recording Command:**
```bash
N_m3u8DL-RE <STREAM_URL> \
  -o <OUTPUT_DIR> \
  --save-name <FILENAME> \
  --max-time <DURATION> \
  -M mp4:H.264
```

### 3. file_handler.py (File Management)

**Core Responsibilities:**
- Local file operations
- Cloud upload integration
- Concurrent operation management
- File cleanup

**FileHandler Methods:**
```python
def get_file_size(file_path: str) -> int
def get_file_size_mb(file_path: str) -> float
def file_exists(file_path: str) -> bool
def delete_file(file_path: str) -> bool
def is_file_too_large(file_path: str) -> bool
async def upload_to_gofile(file_path: str, token: str) -> Tuple[bool, str]
def create_recording_filename(prefix: str) -> str
def cleanup_old_recordings(max_age_hours: int) -> int
```

**ConcurrentRecordingManager Methods:**
```python
async def initialize(self):
    """Setup semaphore for concurrency control"""

async def acquire(user_id: int) -> bool:
    """Acquire slot for new recording"""

async def release(user_id: int):
    """Release recording slot"""

def get_active_count(self) -> int:
    """Get number of active recordings"""

def get_remaining_slots(self) -> int:
    """Get available slots"""

def is_user_recording(user_id: int) -> bool:
    """Check user's recording status"""
```

## Data Flow Diagrams

### Recording Flow

```
User: /record HH:MM:SS
         │
         ▼
    validate_duration()
         │
         ▼
    acquire_recording_slot()
         │
         ├─ No slot ──> Reply error
         │
         ▼ (slot acquired)
    show_method_selection()
         │
         ▼
    User selects method
         │
         ▼
    show_delivery_selection()
         │
         ▼
    User selects delivery
         │
         ▼
    start_recording()
         │
         ├─ Create RecorderFactory instance
         │
         ├─ Start subprocess (FFmpeg or N_m3u8DL-RE)
         │
         ├─ Monitor progress every 2 seconds
         │ │
         │ └─ Update message with progress
         │
         ├─ Wait for process completion
         │
         ▼
    recording_success?
         │
         ├─ No ──> Reply error + cleanup
         │
         ▼ (success)
    upload_file()
         │
         ├─ telegram ──> upload_to_telegram()
         │
         └─ gofile ──> upload_to_gofile()
         │
         ▼
    Reply success
         │
         ▼
    cleanup_state()
         │
         ▼
    delete_recording_file()
         │
         ▼
    release_slot()
```

### Concurrent Recording Management

```
User1: /record 01:00:00 ──┐
                           │
User2: /record 00:30:00 ──┤──> Semaphore (max 3)
                           │
User3: /record 00:45:00 ──┤
                           │
User4: /record 00:20:00 ──┘ ──> Queued (slot full)

Recording 1: [████████████░░░░░░░░░░░░] 50%
Recording 2: [████░░░░░░░░░░░░░░░░░░░░] 20%
Recording 3: [██████████████░░░░░░░░░░] 45%
```

## Error Handling Strategy

### Recording Phase

```python
try:
    # Start recording
    recorder = RecorderFactory.create(method, url, duration, output)
    success = await recorder.record(progress_callback)
    
    if not success:
        if recorder.cancelled:
            # User cancelled
            await message.edit_text("Recording cancelled")
        else:
            # Recording failed
            await message.edit_text("Recording failed")
except Exception as e:
    # Unexpected error
    await message.reply_text(f"Error: {str(e)}")
finally:
    # Always cleanup
    await cleanup_and_release()
```

### Upload Phase

```python
try:
    if delivery == "telegram":
        await upload_to_telegram(...)
    elif delivery == "gofile":
        success, link = await file_handler.upload_to_gofile(...)
except FloodWait as e:
    # Telegram rate limit
    await asyncio.sleep(e.value)
    # Retry logic
except Exception as e:
    # Other errors
    await message.reply_text(f"Upload failed: {str(e)}")
```

## Configuration Management

### Environment Variables Hierarchy

```
1. .env file (highest priority)
   ↓
2. OS environment variables
   ↓
3. Default values in code (lowest priority)
```

### Configuration Validation

```python
if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
    logger.error("Missing required configuration")
    sys.exit(1)

# Validation on startup
if MAX_CONCURRENT_RECORDINGS < 1:
    raise ValueError("MAX_CONCURRENT_RECORDINGS must be >= 1")

if MAX_FILE_SIZE_MB < 100:
    raise ValueError("MAX_FILE_SIZE_MB must be >= 100")
```

## Logging Strategy

### Log Levels

```
DEBUG     - Detailed variable states, entry/exit of functions
INFO      - General flow (bot started, recording started, completed)
WARNING   - Non-critical issues (slow connection, large file)
ERROR     - Failures (recording failed, upload failed)
CRITICAL  - System failures (database connection, bot crash)
```

### Log Format

```
2026-02-20 14:30:45,123 - bot - INFO - Starting FFmpeg recording for user 12345
2026-02-20 14:35:47,456 - recording - INFO - FFmpeg recording completed: /path/to/file.mkv
2026-02-20 14:35:50,789 - file_handler - INFO - Successfully uploaded to GoFile: https://gofile.io/d/xyz
```

### Log Files

```
sony_bot.log          - Main bot activity
recordings/           - Recording files
docker-compose.log    - Docker container logs
```

## Performance Considerations

### CPU/Memory Usage

| Operation | CPU Usage | Memory Usage | Notes |
|-----------|-----------|--------------|-------|
| FFmpeg Recording | Medium | Low-Medium | Depends on bitrate |
| N_m3u8DL-RE | Low-Medium | Medium | More overhead than FFmpeg |
| Telegram Upload | Low | Medium | Network I/O bound |
| GoFile Upload | Low | Medium | Network I/O bound |

### Concurrency Limits

```python
# Recommended based on resources
Small VM (1 CPU, 1GB RAM):    MAX_CONCURRENT_RECORDINGS = 1
Medium VM (2 CPU, 4GB RAM):   MAX_CONCURRENT_RECORDINGS = 2-3
Large VM (4+ CPU, 8GB+ RAM):  MAX_CONCURRENT_RECORDINGS = 4-5
```

### Disk Space Management

```python
# Monitor recording directory
du -sh ./recordings

# Cleanup strategy
# - Auto-delete after successful upload
# - Manual cleanup of failed recordings
# - Periodic old file deletion (optional)

cleanup_old_recordings(max_age_hours=24)
```

## Security Considerations

### Sensitive Data

```
.env                  - Contains API keys, tokens
BOT_TOKEN            - Telegram bot access
GOFILE_TOKEN         - GoFile API access
Recording files      - May contain copyrighted content
```

### Best Practices

1. **Never commit .env to version control**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use strong file permissions**
   ```bash
   chmod 600 .env
   chmod 700 recordings/
   ```

3. **Rotate tokens regularly**
   - Generate new BOT_TOKEN from @BotFather
   - Update GoFile token from dashboard

4. **Monitor logs for suspicious activity**
   - Multiple failed login attempts
   - Unusual file sizes
   - API errors

## Testing

### Unit Testing Approach

```python
# Test duration parsing
assert parse_duration("01:30:45") == "01:30:45"
assert parse_duration("invalid") is None

# Test recorder factory
ffmpeg_recorder = RecorderFactory.create("ffmpeg", url, duration, output)
assert isinstance(ffmpeg_recorder, FFmpegRecorder)

# Test file handler
assert file_handler.get_file_size_mb(file) > 0
assert file_handler.is_file_too_large(file) == False
```

### Integration Testing

```python
# Test full recording flow
1. Create user state
2. Start recording (mock subprocess)
3. Update progress
4. Complete recording
5. Verify file exists
6. Test upload
7. Cleanup
```

## Deployment Checklist

- [ ] Telegram API credentials configured
- [ ] Bot token created and added to .env
- [ ] FFmpeg installed (Docker does this)
- [ ] N_m3u8DL-RE available (Docker does this)
- [ ] Recordings directory has write permissions
- [ ] SONY_STREAM_URL verified and accessible
- [ ] GOFILE_TOKEN configured (if using GoFile)
- [ ] Docker and Docker Compose installed
- [ ] Sufficient disk space (at least 10GB)
- [ ] Sufficient bandwidth for concurrent recordings
- [ ] Logs rotation configured
- [ ] Backup strategy for important recordings

## Troubleshooting Guide

### Process-Level Debugging

```python
# Add debug logging in recording.py
logger.debug(f"Starting {method} process: {cmd}")
logger.debug(f"Process PID: {self.process.pid}")
logger.debug(f"Process return code: {self.process.returncode}")
```

### Connection Debugging

```bash
# Test stream URL
curl -I https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8

# Test Telegram API
curl https://api.telegram.org/bot<TOKEN>/getMe

# Monitor network usage
top -p $(pgrep -f "ffmpeg")
```

### File System Debugging

```bash
# Check recordings directory
ls -lh recordings/

# Monitor disk usage
watch -n 1 "du -sh recordings/"

# Check inode count
df -i recordings/
```

---

**Last Updated:** 2026-02-20  
**Version:** 1.0.0  
**Maintainer:** SONY YAY! Bot Team

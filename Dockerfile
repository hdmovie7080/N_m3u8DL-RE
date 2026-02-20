FROM python:3.11-slim

# Install system dependencies including ffmpeg and N_m3u8DL-RE
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install N_m3u8DL-RE
RUN mkdir -p /opt/n_m3u8dl-re && \
    wget -q "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0-beta/N_m3u8DL-RE_linux_x64" \
    -O /opt/n_m3u8dl-re/N_m3u8DL-RE && \
    chmod +x /opt/n_m3u8dl-re/N_m3u8DL-RE && \
    ln -s /opt/n_m3u8dl-re/N_m3u8DL-RE /usr/local/bin/N_m3u8DL-RE || true

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY bot.py .
COPY recording.py .
COPY file_handler.py .
COPY .env .

# Create recordings directory
RUN mkdir -p recordings

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV RECORDINGS_DIR=/app/recordings

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Run the bot
CMD ["python", "bot.py"]

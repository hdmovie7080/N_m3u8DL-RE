#!/bin/bash

# SONY YAY! Recording Bot Startup Script

echo "=================================="
echo "SONY YAY! Recording Bot"
echo "Starting Bot..."
echo "=================================="

# Create recordings directory if it doesn't exist
mkdir -p recordings

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please create .env with required variables:"
    echo "  API_ID"
    echo "  API_HASH"
    echo "  BOT_TOKEN"
    echo "  OWNER_ID"
    exit 1
fi

# Start the bot
echo "Starting bot.py..."
python bot.py

exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo "ERROR: Bot exited with code $exit_code"
    exit $exit_code
fi

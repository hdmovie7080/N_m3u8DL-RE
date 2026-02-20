#!/bin/bash

# SONY YAY! Recording Bot - Installation Verification Script
# This script checks if all dependencies and configurations are properly set up

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}SONY YAY! Bot - Installation Verification${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Function to print test result
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $2"
        ((FAILED++))
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check Python version
echo -e "${BLUE}1. Checking Python...${NC}"
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1)
    print_result 0 "Python found: $python_version"
    
    # Check if version >= 3.8
    python_minor=$(python3 -c 'import sys; print(sys.version_info[1])')
    if [ "$python_minor" -ge 8 ]; then
        print_result 0 "Python version >= 3.8"
    else
        print_result 1 "Python version must be >= 3.8"
    fi
else
    print_result 1 "Python 3 is not installed"
fi
echo

# Check .env file
echo -e "${BLUE}2. Checking .env Configuration...${NC}"
if [ -f ".env" ]; then
    print_result 0 ".env file exists"
    
    # Check required variables
    required_vars=("API_ID" "API_HASH" "BOT_TOKEN" "OWNER_ID")
    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env; then
            value=$(grep "^${var}=" .env | cut -d'=' -f2)
            if [ -z "$value" ] || [ "$value" = "your_value" ]; then
                print_warning "$var is set but appears to be a placeholder"
            else
                print_result 0 "$var is configured"
            fi
        else
            print_result 1 "$var is missing from .env"
        fi
    done
else
    print_result 1 ".env file not found"
    print_info "Copy .env.example to .env and fill in your values:"
    print_info "  cp .env.example .env"
fi
echo

# Check Python dependencies
echo -e "${BLUE}3. Checking Python Dependencies...${NC}"
required_packages=("pyrogram" "aiofiles" "dotenv" "requests")

if [ -f "requirements.txt" ]; then
    print_result 0 "requirements.txt exists"
    
    for package in "${required_packages[@]}"; do
        if grep -q "$package" requirements.txt; then
            print_result 0 "$package is in requirements.txt"
        else
            print_warning "$package is not in requirements.txt"
        fi
    done
else
    print_warning "requirements.txt not found"
fi

# Check if packages are installed
if python3 -c "import pyrogram" 2>/dev/null; then
    print_result 0 "Pyrogram is installed"
else
    print_warning "Pyrogram is not installed (run: pip install -r requirements.txt)"
fi

if python3 -c "import aiofiles" 2>/dev/null; then
    print_result 0 "aiofiles is installed"
else
    print_warning "aiofiles is not installed"
fi
echo

# Check system dependencies
echo -e "${BLUE}4. Checking System Dependencies...${NC}"

# Check FFmpeg
if command -v ffmpeg &> /dev/null; then
    ffmpeg_version=$(ffmpeg -version 2>&1 | head -n 1)
    print_result 0 "FFmpeg installed: $ffmpeg_version"
else
    print_result 1 "FFmpeg is not installed"
    print_info "Install with: sudo apt-get install ffmpeg"
fi

# Check N_m3u8DL-RE
if command -v N_m3u8DL-RE &> /dev/null; then
    print_result 0 "N_m3u8DL-RE is installed"
else
    print_warning "N_m3u8DL-RE is not installed (required for N_m3u8DL-RE recording method)"
    print_info "Download from: https://github.com/nilaoda/N_m3u8DL-RE/releases"
fi

# Check curl
if command -v curl &> /dev/null; then
    print_result 0 "curl is installed"
else
    print_warning "curl is not installed (needed for testing)"
fi
echo

# Check project structure
echo -e "${BLUE}5. Checking Project Structure...${NC}"
required_files=("bot.py" "recording.py" "file_handler.py" ".env" "requirements.txt")

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        print_result 0 "$file exists"
    else
        print_result 1 "$file is missing"
    fi
done
echo

# Check Docker
echo -e "${BLUE}6. Checking Docker Setup...${NC}"
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    print_result 0 "Docker installed: $docker_version"
else
    print_warning "Docker is not installed (required for containerized deployment)"
fi

if command -v docker-compose &> /dev/null; then
    docker_compose_version=$(docker-compose --version)
    print_result 0 "Docker Compose installed: $docker_compose_version"
else
    print_warning "Docker Compose is not installed"
fi

if [ -f "Dockerfile" ]; then
    print_result 0 "Dockerfile exists"
else
    print_result 1 "Dockerfile is missing"
fi

if [ -f "docker-compose.yml" ]; then
    print_result 0 "docker-compose.yml exists"
else
    print_result 1 "docker-compose.yml is missing"
fi
echo

# Check recordings directory
echo -e "${BLUE}7. Checking Recordings Directory...${NC}"
if [ -d "recordings" ]; then
    print_result 0 "recordings directory exists"
    
    # Check permissions
    if [ -w "recordings" ]; then
        print_result 0 "recordings directory is writable"
    else
        print_result 1 "recordings directory is not writable"
    fi
else
    print_info "recordings directory will be created on first use"
fi
echo

# Network test
echo -e "${BLUE}8. Checking Network Connectivity...${NC}"

# Test SONY Stream URL
if command -v curl &> /dev/null; then
    if curl -I --max-time 5 "https://sliv.tgaadi.workers.dev/sonyyaysd.m3u8" 2>/dev/null | grep -q "200\|206\|404"; then
        print_result 0 "SONY stream URL is accessible"
    else
        print_warning "SONY stream URL may not be accessible (verify VPN/Proxy)"
    fi
    
    # Test Telegram API
    if [ -f ".env" ]; then
        bot_token=$(grep "^BOT_TOKEN=" .env | cut -d'=' -f2)
        if [ ! -z "$bot_token" ] && [ "$bot_token" != "your_bot_token" ]; then
            if curl -s "https://api.telegram.org/bot${bot_token}/getMe" | grep -q "ok"; then
                print_result 0 "Telegram API connection successful"
            else
                print_warning "Telegram API connection failed (check BOT_TOKEN)"
            fi
        fi
    fi
else
    print_warning "curl not installed, skipping network tests"
fi
echo

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Verification Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Passed:${NC} $PASSED"
echo -e "${RED}Failed:${NC} $FAILED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed! Bot is ready to run.${NC}"
        echo
        echo -e "${BLUE}Next steps:${NC}"
        echo "1. Update .env with your Telegram credentials"
        echo "2. Run: docker-compose up -d"
        echo "3. Or run: python3 bot.py"
        exit 0
    else
        echo -e "${YELLOW}⚠ Some checks passed with warnings.${NC}"
        echo "Please review the warnings above."
        exit 0
    fi
else
    echo -e "${RED}✗ Some checks failed. Please fix the issues above.${NC}"
    exit 1
fi

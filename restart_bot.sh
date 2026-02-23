#!/bin/bash
# restart_bot.sh - Script to quickly restart the Legend GaldCup Bot

echo "Restarting Legend GaldCup Bot..."

# 1. Stop the bot securely
./stop_bot.sh

# 2. Wait a moment to ensure ports and locks are freed
sleep 2

# 3. Start the bot again without installing dependencies (assuming they are already installed)
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run ./start_bot.sh first."
    exit 1
fi

source venv/bin/activate
echo "Checking and installing any new dependencies..."
pip install -r requirements.txt

echo "Starting the bot in the background..."
nohup python3 main.py > bot.log 2>&1 &
echo "=========================================="
echo "✅ Bot has been restarted!"
echo "New Process ID (PID): $!"
echo "tail -f bot.log to view output."
echo "=========================================="

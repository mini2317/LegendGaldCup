#!/bin/bash
# stop_bot.sh - Script to stop the running Legend GaldCup Bot

echo "Stopping Legend GaldCup Bot..."

# Find the PID of the python3 process running main.py
PID=$(pgrep -f "python3 main.py")

if [ -z "$PID" ]; then
    echo "No running bot process found. (python3 main.py)"
else
    echo "Found bot process with PID: $PID"
    kill $PID
    echo "Bot stopped successfully."
fi

#!/bin/bash
# start_bot.sh - Linux setup & run script for Legend GaldCup Bot

echo "Starting Legend GaldCup Environment Setup..."

# 1. Check if Python 3 is installed, install if missing
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Attempting to install Python 3 and venv..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3 python3-venv
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-venv
    else
        echo "Error: Could not find a supported package manager (apt/yum/dnf). Please install Python 3 manually."
        exit 1
    fi
else
    echo "Python 3 is already installed."
    # Ensure python3-venv is installed on Debian-based systems if venv creation fails later
fi

# 2. Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating python3 virtual environment (venv)..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Attempting to install python3-venv..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y python3-venv
            python3 -m venv venv
        fi
        
        if [ ! -d "venv" ]; then
            echo "Error: Failed to create virtual environment. Please install python3-venv manually."
            exit 1
        fi
    fi
fi

# 3. Activate virtual environment
source venv/bin/activate

# 3. Install required packages
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies."
    exit 1
fi

# 4. Check for .env file
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Please create one based on .env.example before running."
    echo "You can still run this script again once .env is ready."
    exit 1
fi

# 5. Run the bot in the background using nohup
echo "Starting the bot in the background..."
nohup python3 main.py > bot.log 2>&1 &
echo "=========================================="
echo "✅ Bot is now running in the background!"
echo "Process ID (PID): $!"
echo "You can view the live console output by typing: tail -f bot.log"
echo "=========================================="

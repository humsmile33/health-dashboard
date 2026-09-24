#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Project root directory (directory where the script is located)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

echo "=========================================================="
echo "  Daily Briefing Dashboard - Initialization & Update"
echo "=========================================================="

# 1. Setup python virtual environment if not present
if [ ! -d ".venv" ]; then
    echo "[Step 1/3] Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "[Step 1/3] Virtual environment (.venv) already exists."
fi

# 2. Activate virtual environment and install dependencies
echo "[Step 2/3] Activating virtual environment & installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Run the generator script
echo "[Step 3/3] Generating dashboard..."
python update_dashboard.py

# 4. Open the generated dashboard.html in browser
if [ -f "dashboard.html" ]; then
    echo "----------------------------------------------------------"
    echo "[Success] dashboard.html generated successfully!"
    echo "Opening dashboard in your default browser..."
    open "dashboard.html"
else
    echo "[Error] dashboard.html was not generated."
    exit 1
fi

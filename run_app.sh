#!/usr/bin/env bash
# FX Live Analyst — one-click launcher for macOS / Linux
cd "$(dirname "$0")"
echo "Checking libraries (first run may take a minute)..."
pip3 install -q -r requirements.txt
echo "Starting FX Live Analyst... your browser will open automatically."
echo "(Press Ctrl+C in this terminal to stop the app)"
python3 -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false

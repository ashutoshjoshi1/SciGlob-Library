#!/bin/bash
# Quick launcher script for Motor Control GUI

echo "======================================"
echo "  SciGlob Motor Control Launcher"
echo "======================================"
echo ""

# Check if sciglob is installed
if ! python3 -c "import sciglob" 2>/dev/null; then
    echo "⚠️  SciGlob library not found!"
    echo "Installing sciglob..."
    pip3 install sciglob
    echo ""
fi

echo "🚀 Starting Motor Control GUI..."
python3 motor_control_gui.py

#!/bin/bash

##############################################################################
# TP4-ASSD Power Analyzer - Visualizer Setup Script
#
# Installs Python dependencies and runs the STM32 visualizer
##############################################################################

set -e

echo "=================================================="
echo "TP4-ASSD Power Analyzer - Visualizer Setup"
echo "=================================================="

# Check Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION found"

# Create virtual environment (optional but recommended)
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1

DEPS="PyQt5 pyqtgraph pyserial"
echo "Installing: $DEPS"
pip install $DEPS

echo "✓ Dependencies installed"

# Check USB device exists
echo ""
echo "Checking for STM32 USB device..."
if [ -e /dev/ttyUSB0 ]; then
    echo "✓ Found /dev/ttyUSB0"
    USB_PORT="/dev/ttyUSB0"
elif [ -e /dev/ttyUSB1 ]; then
    echo "⚠ Found /dev/ttyUSB1 (using instead)"
    USB_PORT="/dev/ttyUSB1"
elif [ -c /dev/ttyACM0 ]; then
    echo "✓ Found /dev/ttyACM0 (STM32 native CDC)"
    USB_PORT="/dev/ttyACM0"
else
    echo "⚠ No serial device found. Verify STM32 is connected."
    echo "  Run: ls -la /dev/tty* | grep -E '(USB|ACM)'"
    USB_PORT="/dev/ttyUSB0"
fi

# Display ready message
echo ""
echo "=================================================="
echo "✓ Setup complete!"
echo "=================================================="
echo ""
echo "To run the visualizer:"
echo "  1. Make sure STM32 is connected via USB"
echo "  2. Run: python visualizer_main.py"
echo "  3. Select port: $USB_PORT"
echo "  4. Click 'Connect'"
echo ""
echo "To test serial connection first:"
echo "  miniterm.py $USB_PORT 115200"
echo "  (Press Ctrl+] to exit)"
echo ""

# Ask to run now
read -p "Run visualizer now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting visualizer..."
    python visualizer_main.py
else
    echo "Visualizer will start when you run: python visualizer_main.py"
fi

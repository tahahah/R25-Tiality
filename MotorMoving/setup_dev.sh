#!/bin/bash
# Development setup script

echo "Setting up development environment..."

# Check if we're on Raspberry Pi
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Detected Raspberry Pi - installing full dependencies"
    pip3 install RPi.GPIO paho-mqtt pynput
else
    echo "Detected non-Pi system - installing development dependencies"
    pip install paho-mqtt pynput
    echo "Note: RPi.GPIO will not be available (this is normal)"
fi

echo "Setup complete!"

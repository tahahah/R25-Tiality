#!/bin/bash
# Quick script to activate the operator virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv_operator/bin/activate"
echo "Virtual environment activated!"
echo "You can now run: python3 GUI/gui.py --robot --broker_port 2883 --audio"

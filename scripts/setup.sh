#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if command -v python3 &>/dev/null; then
    python3 "$SCRIPT_DIR/configure.py"
elif command -v python &>/dev/null; then
    python "$SCRIPT_DIR/configure.py"
else
    echo "Error: Python is not installed. Please install Python to run the setup script."
    exit 1
fi

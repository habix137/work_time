#!/bin/bash

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Virtual environment activated."
else
    echo "Error: venv directory not found. Create it first with 'python -m venv venv'."
    exit 1
fi

# Install requirements
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "Requirements installed."
else
    echo "Error: requirements.txt not found."
    exit 1
fi

# Run the project
echo "Starting Flask app..."
python module/main.py

#!/bin/bash
# To run this application: ./start.sh

echo "--- Starting Range Gap Finder v2 Application ---"

# --- Dynamically find the project's root directory ---
# Get the directory where this script is located.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# The project root is one level up from the script's directory.
PROJECT_ROOT="$SCRIPT_DIR/.."

echo "Project root identified as: $PROJECT_ROOT"

# --- CRITICAL: Change into the project root directory ---
# This ensures that 'venv' and the 'Procfile' are found correctly.
cd "$PROJECT_ROOT"

echo "Current working directory set to: $(pwd)"
echo ""

# Set environment variable to suppress tokenizer parallelism warning.
export TOKENIZERS_PARALLELISM=false

# Activate the Python virtual environment from the project root.
source "venv/bin/activate"

# Ensure Redis is running via Docker.
if [ ! "$(docker ps -q -f name=redis)" ]; then
    if [ "$(docker ps -aq -f status=exited -f name=redis)" ]; then
        # cleanup
        docker rm redis
    fi
    # run
    echo "Starting Redis container..."
    docker run -d --name redis -p 6379:6379 redis
else
    echo "Redis container is already running."
fi

echo ""
echo "Starting application with honcho..."

# Start all processes defined in the Procfile.
# Honcho will now find the Procfile in the current directory.
honcho start
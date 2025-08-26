#!/bin/bash

# Range Gap Finder - Startup Script
# This script sets up and starts the Range Gap Finder application

set -e  # Exit on any error

echo "🚀 Starting Range Gap Finder..."

# Check if Python 3.8+ is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python version $PYTHON_VERSION is too old. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detected"

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker to run Redis."
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo "❌ Docker daemon is not running. Please start Docker."
    exit 1
fi

echo "✅ Docker is running"

# Start Redis if not already running
if ! docker ps | grep -q redis; then
    echo "🔧 Starting Redis container..."
    docker run -d --name redis-cache -p 6379:6379 redis:alpine
    echo "✅ Redis container started"
else
    echo "✅ Redis container is already running"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r scripts/requirements.txt

# Download spaCy model if not already downloaded
echo "📚 Downloading spaCy model..."
python3 -m spacy download en_core_web_sm

# Download NLTK data
echo "📚 Downloading NLTK data..."
python3 -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

# Create cachedir if it doesn't exist
mkdir -p cachedir

echo "🎯 Starting Range Gap Finder application..."

# Start the application using honcho (process manager)
echo "🌐 Starting web server and worker processes..."
honcho start

echo "✅ Range Gap Finder is now running!"
echo "🌍 Open your browser and go to: http://localhost:5000"
echo ""
echo "To stop the application, press Ctrl+C"
echo "To stop Redis: docker stop redis-cache"

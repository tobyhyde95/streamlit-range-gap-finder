#!/bin/bash

# Range Gap Finder - Startup Script (No Docker Required)
# This script sets up and starts the Range Gap Finder application
# All dependencies run locally without Docker

set -e  # Exit on error (but allow some commands to fail gracefully)

echo "🚀 Starting Range Gap Finder (No Docker Required)..."
echo ""

# ============================================================================
# PREREQUISITE CHECKS
# ============================================================================

# Check if Python 3.8+ is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    echo ""
    echo "Installation instructions:"
    echo "  macOS:   brew install python3"
    echo "  Ubuntu:  sudo apt-get install python3 python3-pip"
    echo "  CentOS:  sudo yum install python3 python3-pip"
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

# Check if pip3 is available
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip3."
    echo ""
    echo "Installation instructions:"
    echo "  macOS:   brew install python3"
    echo "  Ubuntu:  sudo apt-get install python3-pip"
    echo "  CentOS:  sudo yum install python3-pip"
    echo "  Or:      python3 -m ensurepip --upgrade"
    exit 1
fi

echo "✅ pip3 is available"

# ============================================================================
# REDIS INSTALLATION (if not present)
# ============================================================================

install_redis() {
    echo ""
    echo "🔧 Redis is not installed. Attempting to install Redis..."
    echo ""
    
    REDIS_INSTALLED=false
    
    # Check if we're running as root (no sudo needed)
    IS_ROOT=false
    if [ "$EUID" -eq 0 ]; then
        IS_ROOT=true
        echo "ℹ️  Running as root - sudo not required"
    fi
    
    # Detect OS and install Redis using appropriate package manager
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            echo "📦 Installing Redis via Homebrew..."
            if brew install redis; then
                REDIS_INSTALLED=true
                echo "✅ Redis installed successfully via Homebrew"
            else
                echo "❌ Failed to install Redis via Homebrew"
            fi
        else
            echo "❌ Homebrew not found. Please install Homebrew first:"
            echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo ""
            echo "   Then install Redis manually: brew install redis"
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux - detect distribution
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO=$ID
        else
            DISTRO="unknown"
        fi
        
        case $DISTRO in
            ubuntu|debian)
                if [ "$IS_ROOT" = false ] && ! command -v sudo &> /dev/null; then
                    echo "❌ sudo is required but not available"
                    echo "   Please run as root or install sudo"
                    return 1
                fi
                echo "📦 Installing Redis via apt-get..."
                if [ "$IS_ROOT" = false ]; then
                    echo "   (You may be prompted for your sudo password)"
                    SUDO_CMD="sudo"
                else
                    SUDO_CMD=""
                fi
                if $SUDO_CMD apt-get update && $SUDO_CMD apt-get install -y redis-server; then
                    REDIS_INSTALLED=true
                    echo "✅ Redis installed successfully via apt-get"
                else
                    echo "❌ Failed to install Redis via apt-get"
                    echo "   You may need to run: sudo apt-get install redis-server"
                fi
                ;;
            centos|rhel|fedora)
                if [ "$IS_ROOT" = false ] && ! command -v sudo &> /dev/null; then
                    echo "❌ sudo is required but not available"
                    echo "   Please run as root or install sudo"
                    return 1
                fi
                if [ "$IS_ROOT" = false ]; then
                    SUDO_CMD="sudo"
                    echo "   (You may be prompted for your sudo password)"
                else
                    SUDO_CMD=""
                fi
                if command -v dnf &> /dev/null; then
                    echo "📦 Installing Redis via dnf..."
                    if $SUDO_CMD dnf install -y redis; then
                        REDIS_INSTALLED=true
                        echo "✅ Redis installed successfully via dnf"
                    else
                        echo "❌ Failed to install Redis via dnf"
                        echo "   You may need to run: sudo dnf install redis"
                    fi
                elif command -v yum &> /dev/null; then
                    echo "📦 Installing Redis via yum..."
                    if $SUDO_CMD yum install -y redis; then
                        REDIS_INSTALLED=true
                        echo "✅ Redis installed successfully via yum"
                    else
                        echo "❌ Failed to install Redis via yum"
                        echo "   You may need to run: sudo yum install redis"
                    fi
                fi
                ;;
            arch|manjaro)
                if [ "$IS_ROOT" = false ] && ! command -v sudo &> /dev/null; then
                    echo "❌ sudo is required but not available"
                    echo "   Please run as root or install sudo"
                    return 1
                fi
                echo "📦 Installing Redis via pacman..."
                if [ "$IS_ROOT" = false ]; then
                    echo "   (You may be prompted for your sudo password)"
                    SUDO_CMD="sudo"
                else
                    SUDO_CMD=""
                fi
                if $SUDO_CMD pacman -S --noconfirm redis; then
                    REDIS_INSTALLED=true
                    echo "✅ Redis installed successfully via pacman"
                else
                    echo "❌ Failed to install Redis via pacman"
                    echo "   You may need to run: sudo pacman -S redis"
                fi
                ;;
            *)
                echo "⚠️  Unsupported Linux distribution: $DISTRO"
                echo "   Please install Redis manually for your distribution."
                echo "   Visit: https://redis.io/download"
                ;;
        esac
    else
        echo "⚠️  Unsupported operating system: $OSTYPE"
        echo "   Please install Redis manually."
        echo "   Visit: https://redis.io/download"
    fi
    
    if [ "$REDIS_INSTALLED" = false ]; then
        echo ""
        echo "❌ Automatic Redis installation failed."
        echo ""
        echo "Please install Redis manually using one of these methods:"
        echo "  macOS:   brew install redis"
        echo "  Ubuntu:  sudo apt-get install redis-server"
        echo "  Debian:  sudo apt-get install redis-server"
        echo "  CentOS:  sudo yum install redis"
        echo "  Fedora:  sudo dnf install redis"
        echo "  Arch:    sudo pacman -S redis"
        echo ""
        echo "Or visit: https://redis.io/download"
        exit 1
    fi
    
    # Verify Redis was installed
    sleep 1
    if command -v redis-cli &> /dev/null || command -v redis-server &> /dev/null; then
        echo "✅ Redis installation verified"
        return 0
    else
        echo "⚠️  Redis installation completed but redis-cli/redis-server not found in PATH"
        echo "   You may need to restart your terminal or add Redis to your PATH"
        exit 1
    fi
}

# Check if Redis is installed locally
if ! command -v redis-cli &> /dev/null && ! command -v redis-server &> /dev/null; then
    install_redis
else
    echo "✅ Redis is installed"
fi

# ============================================================================
# REDIS SETUP AND VERIFICATION
# ============================================================================

# Check if Redis is already running
REDIS_RUNNING=false
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        REDIS_RUNNING=true
    fi
fi

if [ "$REDIS_RUNNING" = false ]; then
    echo ""
    echo "🔧 Starting Redis server..."
    
    REDIS_STARTED=false
    
    # Try to start Redis using different methods based on the system
    if command -v brew &> /dev/null; then
        # macOS with Homebrew services
        if brew services list 2>/dev/null | grep -q redis || brew list redis &> /dev/null; then
            if brew services start redis 2>/dev/null; then
                REDIS_STARTED=true
                echo "✅ Redis started via Homebrew services"
            fi
        fi
    fi
    
    if [ "$REDIS_STARTED" = false ] && command -v systemctl &> /dev/null; then
        # Linux with systemd
        if systemctl is-enabled redis &> /dev/null 2>&1 || \
           systemctl list-unit-files 2>/dev/null | grep -q redis.service || \
           systemctl list-unit-files 2>/dev/null | grep -q redis-server.service; then
            if sudo systemctl start redis 2>/dev/null || sudo systemctl start redis-server 2>/dev/null; then
                REDIS_STARTED=true
                echo "✅ Redis started via systemd"
            fi
        fi
    fi
    
    if [ "$REDIS_STARTED" = false ] && command -v service &> /dev/null; then
        # Linux with service command
        if service redis status &> /dev/null || service redis-server status &> /dev/null || [ -f /etc/init.d/redis ] || [ -f /etc/init.d/redis-server ]; then
            if sudo service redis start 2>/dev/null || sudo service redis-server start 2>/dev/null; then
                REDIS_STARTED=true
                echo "✅ Redis started via service command"
            fi
        fi
    fi
    
    if [ "$REDIS_STARTED" = false ] && command -v redis-server &> /dev/null; then
        # Start Redis directly in the background
        if redis-server --daemonize yes 2>/dev/null; then
            REDIS_STARTED=true
            echo "✅ Redis started directly"
        fi
    fi
    
    if [ "$REDIS_STARTED" = false ]; then
        echo ""
        echo "⚠️  Could not automatically start Redis."
        echo "   Please start Redis manually and run this script again."
        echo ""
        echo "   Try one of these commands:"
        echo "     macOS:   brew services start redis"
        echo "     Linux:   sudo systemctl start redis"
        echo "     Linux:   sudo systemctl start redis-server"
        echo "     Direct:  redis-server --daemonize yes"
        exit 1
    fi
    
    # Wait for Redis to start and verify it's running
    echo "⏳ Waiting for Redis to start..."
    for i in {1..10}; do
        if redis-cli ping &> /dev/null; then
            break
        fi
        sleep 1
    done
    
    # Verify Redis is running
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis is now running and responding"
    else
        echo "❌ Redis failed to start or is not responding."
        echo "   Please check Redis logs and try again."
        echo "   You can check Redis status with: redis-cli ping"
        exit 1
    fi
else
    echo "✅ Redis is already running"
fi

# Final Redis connection test
if ! redis-cli ping &> /dev/null; then
    echo "❌ Cannot connect to Redis. Please ensure Redis is running on localhost:6379"
    exit 1
fi

# ============================================================================
# PYTHON DEPENDENCIES SETUP
# ============================================================================

echo ""
echo "📦 Installing Python dependencies..."

# Check if requirements file exists
if [ ! -f "scripts/requirements.txt" ]; then
    echo "❌ Requirements file not found at scripts/requirements.txt"
    exit 1
fi

# Install dependencies (continue even if some packages are already installed)
set +e  # Temporarily disable exit on error for pip install
pip3 install -r scripts/requirements.txt
PIP_EXIT_CODE=$?
set -e  # Re-enable exit on error

if [ $PIP_EXIT_CODE -ne 0 ]; then
    echo "⚠️  Some dependencies may have failed to install (exit code: $PIP_EXIT_CODE)."
    echo "   This may be normal if packages are already installed."
    echo "   Continuing anyway..."
fi

echo "✅ Python dependencies installed"

# ============================================================================
# NLP MODEL SETUP
# ============================================================================

echo ""
echo "📚 Setting up NLP models..."

# Download spaCy model if not already downloaded
echo "  - Downloading spaCy model (en_core_web_sm)..."
if python3 -m spacy download en_core_web_sm 2>/dev/null; then
    echo "  ✅ spaCy model ready"
else
    echo "  ⚠️  spaCy model download had issues (may already be installed)"
fi

# Download NLTK data
echo "  - Downloading NLTK data..."
if python3 -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('wordnet', quiet=True)" 2>/dev/null; then
    echo "  ✅ NLTK data ready"
else
    echo "  ⚠️  NLTK data download had issues (may already be installed)"
fi

# ============================================================================
# DIRECTORY SETUP
# ============================================================================

# Create cachedir if it doesn't exist
mkdir -p cachedir
echo "✅ Cache directory ready"

# ============================================================================
# APPLICATION STARTUP
# ============================================================================

# Check if honcho is installed
if ! command -v honcho &> /dev/null; then
    echo ""
    echo "⚠️  honcho is not installed. Installing it now..."
    pip3 install honcho
fi

# Check if Procfile exists
if [ ! -f "Procfile" ]; then
    echo "❌ Procfile not found. Cannot start application."
    exit 1
fi

echo ""
echo "🎯 Starting Range Gap Finder application..."
echo ""

# Verify Redis connection one more time before starting
if ! redis-cli ping &> /dev/null; then
    echo "❌ Redis connection lost. Please ensure Redis is running."
    exit 1
fi

# Start the application using honcho (process manager)
echo "🌐 Starting web server and worker processes..."
echo ""

# Trap Ctrl+C to provide clean shutdown message
trap 'echo ""; echo "🛑 Shutting down..."; exit 0' INT TERM

honcho start

# This line won't be reached unless honcho exits unexpectedly
echo ""
echo "✅ Range Gap Finder has stopped."
echo ""
echo "To stop Redis later, use one of these commands:"
echo "  macOS (Homebrew): brew services stop redis"
echo "  Linux (systemd):  sudo systemctl stop redis"
echo "  Linux (systemd):  sudo systemctl stop redis-server"
echo "  Linux (service):  sudo service redis stop"
echo "  Direct:           redis-cli shutdown"

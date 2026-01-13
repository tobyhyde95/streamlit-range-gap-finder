#!/usr/bin/env python3
"""
Range Gap Finder - Cross-Platform Startup Script
Works on both Windows and Mac/Linux
"""

import sys
import subprocess
import os
import platform
from pathlib import Path

def run_command(cmd, shell=False, check=True):
    """Run a command and return success status"""
    try:
        if isinstance(cmd, str):
            cmd = cmd.split()
        result = subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr
    except FileNotFoundError:
        return False, "", "Command not found"

def check_command_exists(cmd):
    """Check if a command exists in PATH"""
    if platform.system() == "Windows":
        success, _, _ = run_command(f"where {cmd}", shell=True, check=False)
    else:
        success, _, _ = run_command(f"which {cmd}", shell=False, check=False)
    return success

def get_python_command():
    """Get the appropriate Python command for the platform"""
    if platform.system() == "Windows":
        # Try python first, then python3
        for cmd in ["python", "python3"]:
            if check_command_exists(cmd):
                return cmd
    else:
        # On Mac/Linux, prefer python3
        for cmd in ["python3", "python"]:
            if check_command_exists(cmd):
                return cmd
    return None

def check_python_version():
    """Check if Python 3.8+ is installed"""
    python_cmd = get_python_command()
    if not python_cmd:
        print("❌ Python 3 is not installed. Please install Python 3.8 or higher.")
        sys.exit(1)
    
    try:
        result = subprocess.run(
            [python_cmd, "-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
            capture_output=True,
            text=True,
            check=True
        )
        version_str = result.stdout.strip()
        major, minor = map(int, version_str.split('.'))
        
        if major < 3 or (major == 3 and minor < 8):
            print(f"❌ Python version {version_str} is too old. Please install Python 3.8 or higher.")
            sys.exit(1)
        
        print(f"✅ Python {version_str} detected")
        return python_cmd
    except Exception as e:
        print(f"❌ Error checking Python version: {e}")
        sys.exit(1)

def check_docker():
    """Check if Docker is installed and running"""
    if not check_command_exists("docker"):
        print("❌ Docker is not installed. Please install Docker to run Redis.")
        sys.exit(1)
    
    # Check if Docker daemon is running
    success, _, _ = run_command("docker info", check=False)
    if not success:
        print("❌ Docker daemon is not running. Please start Docker.")
        sys.exit(1)
    
    print("✅ Docker is running")

def start_redis():
    """Start Redis container if not already running"""
    # Check if Redis container is running
    success, output, _ = run_command("docker ps", check=False)
    if success and "redis" in output.lower():
        # Check specifically for redis-cache container
        success, output, _ = run_command("docker ps --filter name=redis-cache", check=False)
        if success and "redis-cache" in output:
            print("✅ Redis container is already running")
            return
    
    print("🔧 Starting Redis container...")
    success, _, error = run_command(
        ["docker", "run", "-d", "--name", "redis-cache", "-p", "6379:6379", "redis:alpine"],
        check=False
    )
    
    if success:
        print("✅ Redis container started")
    else:
        # Container might already exist but stopped
        if "already in use" in error.lower() or "already exists" in error.lower():
            print("🔄 Redis container exists but is stopped. Starting it...")
            run_command(["docker", "start", "redis-cache"], check=False)
            print("✅ Redis container started")
        else:
            print(f"⚠️  Warning: Could not start Redis container: {error}")
            print("   You may need to manually start it with: docker start redis-cache")

def install_dependencies(python_cmd):
    """Install Python dependencies"""
    requirements_file = Path("scripts/requirements.txt")
    if not requirements_file.exists():
        print("⚠️  Warning: scripts/requirements.txt not found. Skipping dependency installation.")
        return
    
    print("📦 Installing Python dependencies...")
    success, _, error = run_command([python_cmd, "-m", "pip", "install", "-r", str(requirements_file)], check=False)
    if not success:
        print(f"⚠️  Warning: Some dependencies may have failed to install: {error}")

def download_spacy_model(python_cmd):
    """Download spaCy model"""
    print("📚 Downloading spaCy model...")
    run_command([python_cmd, "-m", "spacy", "download", "en_core_web_sm"], check=False)

def download_nltk_data(python_cmd):
    """Download NLTK data"""
    print("📚 Downloading NLTK data...")
    nltk_code = "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"
    run_command([python_cmd, "-c", nltk_code], check=False)

def create_cachedir():
    """Create cachedir if it doesn't exist"""
    cachedir = Path("cachedir")
    cachedir.mkdir(exist_ok=True)
    print("✅ Cache directory ready")

def start_application():
    """Start the application using honcho"""
    if not check_command_exists("honcho"):
        print("❌ Honcho is not installed. Installing...")
        python_cmd = get_python_command()
        run_command([python_cmd, "-m", "pip", "install", "honcho"], check=False)
    
    print("🎯 Starting Range Gap Finder application...")
    print("🌐 Starting web server and worker processes...")
    print("")
    print("✅ Range Gap Finder is now running!")
    print("🌍 Open your browser and go to: http://localhost:5000")
    print("")
    print("To stop the application, press Ctrl+C")
    print("To stop Redis: docker stop redis-cache")
    print("")
    
    # Start honcho (this will block until Ctrl+C)
    try:
        subprocess.run(["honcho", "start"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error starting application: {e}")
        sys.exit(1)

def main():
    """Main entry point"""
    print("🚀 Starting Range Gap Finder...")
    print(f"📍 Platform: {platform.system()} {platform.release()}")
    print("")
    
    # Check Python
    python_cmd = check_python_version()
    
    # Check Docker
    check_docker()
    
    # Start Redis
    start_redis()
    
    # Install dependencies
    install_dependencies(python_cmd)
    
    # Download spaCy model
    download_spacy_model(python_cmd)
    
    # Download NLTK data
    download_nltk_data(python_cmd)
    
    # Create cachedir
    create_cachedir()
    
    # Start application
    start_application()

if __name__ == "__main__":
    main()


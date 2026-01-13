@echo off
REM Range Gap Finder - Windows Batch Startup Script

echo 🚀 Starting Range Gap Finder...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    python3 --version >nul 2>&1
    if errorlevel 1 (
        echo ❌ Python 3 is not installed. Please install Python 3.8 or higher.
        pause
        exit /b 1
    )
    set PYTHON_CMD=python3
) else (
    set PYTHON_CMD=python
)

REM Check Python version
for /f "tokens=2" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python %PYTHON_VERSION% detected

REM Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not installed. Please install Docker to run Redis.
    pause
    exit /b 1
)

REM Check if Docker daemon is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker daemon is not running. Please start Docker.
    pause
    exit /b 1
)

echo ✅ Docker is running

REM Start Redis if not already running
docker ps | findstr /i "redis" >nul 2>&1
if errorlevel 1 (
    echo 🔧 Starting Redis container...
    docker run -d --name redis-cache -p 6379:6379 redis:alpine
    if errorlevel 1 (
        echo 🔄 Redis container may already exist. Starting it...
        docker start redis-cache
    )
    echo ✅ Redis container started
) else (
    echo ✅ Redis container is already running
)

REM Install Python dependencies
echo 📦 Installing Python dependencies...
%PYTHON_CMD% -m pip install -r scripts\requirements.txt

REM Download spaCy model
echo 📚 Downloading spaCy model...
%PYTHON_CMD% -m spacy download en_core_web_sm

REM Download NLTK data
echo 📚 Downloading NLTK data...
%PYTHON_CMD% -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

REM Create cachedir if it doesn't exist
if not exist "cachedir" mkdir cachedir

echo 🎯 Starting Range Gap Finder application...

REM Start the application using honcho
echo 🌐 Starting web server and worker processes...
honcho start

echo ✅ Range Gap Finder is now running!
echo 🌍 Open your browser and go to: http://localhost:5000
echo.
echo To stop the application, press Ctrl+C
echo To stop Redis: docker stop redis-cache

pause


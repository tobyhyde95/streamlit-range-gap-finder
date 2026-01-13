# Range Gap Finder - Windows PowerShell Startup Script

Write-Host "🚀 Starting Range Gap Finder..." -ForegroundColor Cyan

# Check if Python is installed
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} else {
    Write-Host "❌ Python 3 is not installed. Please install Python 3.8 or higher." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check Python version
try {
    $version = & $pythonCmd --version 2>&1
    Write-Host "✅ $version detected" -ForegroundColor Green
} catch {
    Write-Host "❌ Error checking Python version" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if Docker is installed
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker is not installed. Please install Docker to run Redis." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if Docker daemon is running
try {
    docker info | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker daemon is not running. Please start Docker." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Start Redis if not already running
$redisRunning = docker ps | Select-String -Pattern "redis" -Quiet
if (-not $redisRunning) {
    Write-Host "🔧 Starting Redis container..." -ForegroundColor Yellow
    try {
        docker run -d --name redis-cache -p 6379:6379 redis:alpine | Out-Null
        Write-Host "✅ Redis container started" -ForegroundColor Green
    } catch {
        Write-Host "🔄 Redis container may already exist. Starting it..." -ForegroundColor Yellow
        docker start redis-cache | Out-Null
        Write-Host "✅ Redis container started" -ForegroundColor Green
    }
} else {
    Write-Host "✅ Redis container is already running" -ForegroundColor Green
}

# Install Python dependencies
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow
& $pythonCmd -m pip install -r scripts\requirements.txt

# Download spaCy model
Write-Host "📚 Downloading spaCy model..." -ForegroundColor Yellow
& $pythonCmd -m spacy download en_core_web_sm

# Download NLTK data
Write-Host "📚 Downloading NLTK data..." -ForegroundColor Yellow
& $pythonCmd -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

# Create cachedir if it doesn't exist
if (-not (Test-Path "cachedir")) {
    New-Item -ItemType Directory -Path "cachedir" | Out-Null
}

Write-Host "🎯 Starting Range Gap Finder application..." -ForegroundColor Cyan

# Start the application using honcho
Write-Host "🌐 Starting web server and worker processes..." -ForegroundColor Yellow
Write-Host ""
Write-Host "✅ Range Gap Finder is now running!" -ForegroundColor Green
Write-Host "🌍 Open your browser and go to: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop the application, press Ctrl+C" -ForegroundColor Yellow
Write-Host "To stop Redis: docker stop redis-cache" -ForegroundColor Yellow
Write-Host ""

honcho start


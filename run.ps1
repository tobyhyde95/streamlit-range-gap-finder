# Range Gap Finder - Windows PowerShell Startup Script (No Docker Required)

Write-Host "🚀 Starting Range Gap Finder (No Docker Required)..." -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# PREREQUISITE CHECKS
# ============================================================================

# Check if Python is installed and in PATH
$pythonCmd = $null
$pythonFound = $false

if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
    $pythonFound = $true
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
    $pythonFound = $true
} else {
    Write-Host "❌ Python is not found in your PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "IMPORTANT: Installing the Python extension in VS Code does NOT install Python itself!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Checking common Python installation locations..." -ForegroundColor Cyan
    
    # Common Python installation locations on Windows
    $pythonPaths = @(
        "C:\Program Files\Python3*",
        "C:\Program Files (x86)\Python3*",
        "$env:LOCALAPPDATA\Programs\Python\Python3*",
        "$env:USERPROFILE\AppData\Local\Programs\Python\Python3*",
        "C:\Python3*"
    )
    
    foreach ($pathPattern in $pythonPaths) {
        $pythonDirs = Get-ChildItem -Path $pathPattern -ErrorAction SilentlyContinue | Where-Object { $_.PSIsContainer }
        foreach ($pythonDir in $pythonDirs) {
            $pythonExe = Join-Path $pythonDir.FullName "python.exe"
            if (Test-Path $pythonExe) {
                $pythonCmd = $pythonExe
                $pythonFound = $true
                Write-Host "✅ Found Python installation (not in PATH)" -ForegroundColor Green
                Write-Host "   Location: $pythonExe" -ForegroundColor Cyan
                Write-Host ""
                Write-Host "⚠️  WARNING: Python is not in your PATH." -ForegroundColor Yellow
                Write-Host "   To fix this permanently:" -ForegroundColor Yellow
                Write-Host "   1. Add Python folder to Windows PATH environment variable" -ForegroundColor Cyan
                Write-Host "   2. Or reinstall Python and check 'Add Python to PATH'" -ForegroundColor Cyan
                Write-Host ""
                break
            }
        }
        if ($pythonFound) { break }
    }
    
    # Try Python Launcher (py.exe) - Windows 10+
    if (-not $pythonFound) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $pythonCmd = "py"
            $pythonFound = $true
            Write-Host "✅ Found Python Launcher (py.exe)" -ForegroundColor Green
        }
    }
    
    if (-not $pythonFound) {
        Write-Host "❌ Python 3 is not installed on your system." -ForegroundColor Red
        Write-Host ""
        Write-Host "To install Python:" -ForegroundColor Yellow
        Write-Host "  1. Download from: https://www.python.org/downloads/" -ForegroundColor Cyan
        Write-Host "  2. Run the installer" -ForegroundColor Cyan
        Write-Host "  3. IMPORTANT: Check 'Add Python to PATH' during installation" -ForegroundColor Cyan
        Write-Host "  4. Restart your terminal/PowerShell after installation" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "NOTE: The Python extension in VS Code is just an editor tool." -ForegroundColor Yellow
        Write-Host "      You need to install Python itself from python.org" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
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

# Check if pip is available
try {
    & $pythonCmd -m pip --version | Out-Null
    Write-Host "✅ pip is available" -ForegroundColor Green
} catch {
    Write-Host "❌ pip is not available. Please install pip." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ============================================================================
# REDIS INSTALLATION AND SETUP
# ============================================================================

function Install-Redis {
    Write-Host ""
    Write-Host "🔧 Redis is not installed. Attempting to install Redis..." -ForegroundColor Yellow
    Write-Host ""
    
    $redisInstalled = $false
    
    # Try Chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "📦 Installing Redis via Chocolatey..." -ForegroundColor Yellow
        try {
            choco install redis-64 -y
            if ($LASTEXITCODE -eq 0) {
                $redisInstalled = $true
                Write-Host "✅ Redis installed successfully via Chocolatey" -ForegroundColor Green
            }
        } catch {
            Write-Host "⚠️  Chocolatey installation failed" -ForegroundColor Yellow
        }
    }
    
    # Try winget
    if (-not $redisInstalled -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "📦 Installing Redis via winget..." -ForegroundColor Yellow
        try {
            winget install Redis.Redis
            if ($LASTEXITCODE -eq 0) {
                $redisInstalled = $true
                Write-Host "✅ Redis installed successfully via winget" -ForegroundColor Green
            }
        } catch {
            Write-Host "⚠️  winget installation failed" -ForegroundColor Yellow
        }
    }
    
    if (-not $redisInstalled) {
        Write-Host "❌ Could not automatically install Redis." -ForegroundColor Red
        Write-Host ""
        Write-Host "Please install Redis manually using one of these methods:" -ForegroundColor Yellow
        Write-Host "  1. Chocolatey: choco install redis-64" -ForegroundColor Cyan
        Write-Host "  2. winget: winget install Redis.Redis" -ForegroundColor Cyan
        Write-Host "  3. Download from: https://github.com/microsoftarchive/redis/releases" -ForegroundColor Cyan
        Write-Host "  4. Use WSL: Install Redis in Windows Subsystem for Linux" -ForegroundColor Cyan
        Write-Host ""
        return $false
    }
    
    # Refresh environment variables
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Start-Sleep -Seconds 2
    
    return $true
}

function Start-Redis {
    Write-Host ""
    Write-Host "🔧 Starting Redis server..." -ForegroundColor Yellow
    
    # Check if Redis service exists and is running
    $service = Get-Service -Name Redis -ErrorAction SilentlyContinue
    if ($service) {
        if ($service.Status -eq "Running") {
            Write-Host "✅ Redis service is already running" -ForegroundColor Green
            return $true
        } else {
            Write-Host "Starting Redis service..." -ForegroundColor Yellow
            Start-Service -Name Redis -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
            if ((Get-Service -Name Redis).Status -eq "Running") {
                Write-Host "✅ Redis service started" -ForegroundColor Green
                return $true
            }
        }
    }
    
    # Try to run redis-server directly
    if (Get-Command redis-server -ErrorAction SilentlyContinue) {
        Write-Host "⚠️  Starting Redis directly..." -ForegroundColor Yellow
        Write-Host "   Note: Redis will run in a separate window." -ForegroundColor Yellow
        Start-Process -FilePath "redis-server" -WindowStyle Normal
        Start-Sleep -Seconds 3
    }
    
    # Verify Redis is running
    if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
        try {
            $result = & redis-cli ping 2>&1
            if ($result -eq "PONG") {
                Write-Host "✅ Redis is now running" -ForegroundColor Green
                return $true
            }
        } catch {
            # Redis might not be ready yet
        }
    }
    
    Write-Host "❌ Redis failed to start. Please start Redis manually." -ForegroundColor Red
    Write-Host "   Try: redis-server" -ForegroundColor Yellow
    Write-Host "   Or install Redis as a service: choco install redis-64" -ForegroundColor Yellow
    return $false
}

# Check if Redis is installed
$redisInstalled = (Get-Command redis-cli -ErrorAction SilentlyContinue) -or (Get-Command redis-server -ErrorAction SilentlyContinue)

if (-not $redisInstalled) {
    if (-not (Install-Redis)) {
        Read-Host "Press Enter to exit"
        exit 1
    }
    # Re-check after installation
    $redisInstalled = (Get-Command redis-cli -ErrorAction SilentlyContinue) -or (Get-Command redis-server -ErrorAction SilentlyContinue)
}

if ($redisInstalled) {
    Write-Host "✅ Redis is installed" -ForegroundColor Green
} else {
    Write-Host "❌ Redis installation verification failed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if Redis is running
$redisRunning = $false
if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
    try {
        $result = & redis-cli ping 2>&1
        if ($result -eq "PONG") {
            $redisRunning = $true
        }
    } catch {
        # Redis not running
    }
}

if (-not $redisRunning) {
    if (-not (Start-Redis)) {
        Read-Host "Press Enter to exit"
        exit 1
    }
    
    # Final verification
    Start-Sleep -Seconds 2
    try {
        $result = & redis-cli ping 2>&1
        if ($result -ne "PONG") {
            Write-Host "❌ Cannot connect to Redis. Please ensure Redis is running on localhost:6379" -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    } catch {
        Write-Host "❌ Cannot connect to Redis. Please ensure Redis is running on localhost:6379" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "✅ Redis is already running" -ForegroundColor Green
}

# ============================================================================
# PYTHON DEPENDENCIES SETUP
# ============================================================================

Write-Host ""
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow

if (-not (Test-Path "scripts\requirements.txt")) {
    Write-Host "❌ Requirements file not found at scripts\requirements.txt" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

& $pythonCmd -m pip install -r scripts\requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Some dependencies may have failed to install." -ForegroundColor Yellow
    Write-Host "   Continuing anyway..." -ForegroundColor Yellow
}

# ============================================================================
# NLP MODEL SETUP
# ============================================================================

Write-Host ""
Write-Host "📚 Setting up NLP models..." -ForegroundColor Yellow

Write-Host "  - Downloading spaCy model..." -ForegroundColor Cyan
& $pythonCmd -m spacy download en_core_web_sm 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ spaCy model ready" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  spaCy model download had issues (may already be installed)" -ForegroundColor Yellow
}

Write-Host "  - Downloading NLTK data..." -ForegroundColor Cyan
& $pythonCmd -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('wordnet', quiet=True)" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ NLTK data ready" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  NLTK data download had issues (may already be installed)" -ForegroundColor Yellow
}

# ============================================================================
# DIRECTORY SETUP
# ============================================================================

if (-not (Test-Path "cachedir")) {
    New-Item -ItemType Directory -Path "cachedir" | Out-Null
}
Write-Host "✅ Cache directory ready" -ForegroundColor Green

# ============================================================================
# APPLICATION STARTUP
# ============================================================================

# Check if honcho is installed
if (-not (Get-Command honcho -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "⚠️  honcho is not installed. Installing it now..." -ForegroundColor Yellow
    & $pythonCmd -m pip install honcho
}

# Check if Procfile exists
if (-not (Test-Path "Procfile")) {
    Write-Host "❌ Procfile not found. Cannot start application." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Final Redis connection test
try {
    $result = & redis-cli ping 2>&1
    if ($result -ne "PONG") {
        Write-Host "❌ Cannot connect to Redis. Please ensure Redis is running." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} catch {
    Write-Host "❌ Cannot connect to Redis. Please ensure Redis is running." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "🎯 Starting Range Gap Finder application..." -ForegroundColor Cyan
Write-Host "🌐 Starting web server and worker processes..." -ForegroundColor Yellow
Write-Host ""

# Trap Ctrl+C for clean shutdown
$null = Register-EngineEvent PowerShell.Exiting -Action {
    Write-Host ""
    Write-Host "🛑 Shutting down..." -ForegroundColor Yellow
}

Write-Host "✅ Range Gap Finder is now running!" -ForegroundColor Green
Write-Host "🌍 Open your browser and go to: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop the application, press Ctrl+C" -ForegroundColor Yellow
Write-Host "To stop Redis:" -ForegroundColor Yellow
Write-Host "  If installed as service: net stop Redis" -ForegroundColor Cyan
Write-Host "  If running directly: Close the Redis window" -ForegroundColor Cyan
Write-Host ""

honcho start

Write-Host ""
Write-Host "✅ Range Gap Finder has stopped." -ForegroundColor Green

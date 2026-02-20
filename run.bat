@echo off
REM Range Gap Finder - Windows Batch Startup Script (No Docker Required)

echo 🚀 Starting Range Gap Finder (No Docker Required)...
echo.

REM Check if Python is installed and in PATH
set PYTHON_CMD=
python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
) else (
    python3 --version >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=python3
    ) else (
        REM Try Python Launcher (py.exe) - Windows 10+
        py --version >nul 2>&1
        if not errorlevel 1 (
            set PYTHON_CMD=py
        )
    )
)

REM If Python not found in PATH, search common locations
if "%PYTHON_CMD%"=="" (
    echo ❌ Python is not found in your PATH.
    echo.
    echo IMPORTANT: Installing the Python extension in VS Code does NOT install Python itself!
    echo.
    echo Checking common Python installation locations...
    echo.
    
    REM Check Python Launcher first (most reliable on Windows)
    py --version >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=py
        goto python_found_location
    )
    
    REM Check common installation directories
    for /d %%i in ("C:\Program Files\Python3*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_CMD=%%i\python.exe"
            goto python_found_location
        )
    )
    
    for /d %%i in ("C:\Program Files (x86)\Python3*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_CMD=%%i\python.exe"
            goto python_found_location
        )
    )
    
    for /d %%i in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_CMD=%%i\python.exe"
            goto python_found_location
        )
    )
    
    for /d %%i in ("%USERPROFILE%\AppData\Local\Programs\Python\Python3*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_CMD=%%i\python.exe"
            goto python_found_location
        )
    )
    
    for /d %%i in ("C:\Python3*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_CMD=%%i\python.exe"
            goto python_found_location
        )
    )
    
    REM Python not found anywhere
    echo ❌ Python 3 is not installed on your system.
    echo.
    echo To install Python:
    echo   1. Download from: https://www.python.org/downloads/
    echo   2. Run the installer
    echo   3. IMPORTANT: Check "Add Python to PATH" during installation
    echo   4. Restart your terminal/PowerShell after installation
    echo.
    echo NOTE: The Python extension in VS Code is just an editor tool.
    echo        You need to install Python itself from python.org
    echo.
    pause
    exit /b 1
    
    :python_found_location
    echo ✅ Found Python installation (not in PATH)
    echo    Using: %PYTHON_CMD%
    echo.
    echo ⚠️  WARNING: Python is not in your PATH.
    echo    To fix this permanently:
    echo    1. Find Python installation folder: %PYTHON_CMD%
    echo    2. Add it to Windows PATH environment variable
    echo    3. Or reinstall Python and check "Add Python to PATH"
    echo.
)

REM Check Python version
for /f "tokens=2" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python %PYTHON_VERSION% detected

REM Check if pip is available
%PYTHON_CMD% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip is not available. Please install pip.
    pause
    exit /b 1
)
echo ✅ pip is available

REM ============================================================================
REM REDIS INSTALLATION AND SETUP
REM ============================================================================

REM Check if Redis is installed
where redis-cli >nul 2>&1
if errorlevel 1 (
    where redis-server >nul 2>&1
    if errorlevel 1 (
        echo.
        echo 🔧 Redis is not installed. Attempting to install Redis...
        echo.
        
        REM Try Chocolatey
        where choco >nul 2>&1
        if not errorlevel 1 (
            echo 📦 Installing Redis via Chocolatey...
            choco install redis-64 -y
            if not errorlevel 1 (
                echo ✅ Redis installed successfully via Chocolatey
                goto redis_installed
            )
        )
        
        REM Try winget
        where winget >nul 2>&1
        if not errorlevel 1 (
            echo 📦 Installing Redis via winget...
            winget install Redis.Redis
            if not errorlevel 1 (
                echo ✅ Redis installed successfully via winget
                goto redis_installed
            )
        )
        
        echo ❌ Could not automatically install Redis.
        echo.
        echo Please install Redis manually using one of these methods:
        echo   1. Chocolatey: choco install redis-64
        echo   2. winget: winget install Redis.Redis
        echo   3. Download from: https://github.com/microsoftarchive/redis/releases
        echo   4. Use WSL: Install Redis in Windows Subsystem for Linux
        echo.
        pause
        exit /b 1
        
        :redis_installed
        REM Refresh PATH to find newly installed Redis
        call refreshenv >nul 2>&1
        timeout /t 2 /nobreak >nul
    )
)

echo ✅ Redis is installed

REM Check if Redis is running
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo.
    echo 🔧 Starting Redis server...
    
    REM Try to start Redis as a Windows service
    sc query Redis >nul 2>&1
    if not errorlevel 1 (
        sc query Redis | findstr /i "RUNNING" >nul 2>&1
        if errorlevel 1 (
            echo Starting Redis service...
            net start Redis
            timeout /t 3 /nobreak >nul
        ) else (
            echo ✅ Redis service is already running
            goto redis_running
        )
    )
    
    REM Try to run redis-server directly
    where redis-server >nul 2>&1
    if not errorlevel 1 (
        echo ⚠️  Starting Redis directly...
        echo    Note: Redis will run in a separate window.
        start "Redis Server" redis-server
        timeout /t 3 /nobreak >nul
    )
    
    REM Verify Redis is running
    redis-cli ping >nul 2>&1
    if errorlevel 1 (
        echo ❌ Redis failed to start. Please start Redis manually.
        echo    Try: redis-server
        echo    Or install Redis as a service: choco install redis-64
        pause
        exit /b 1
    )
    
    :redis_running
    echo ✅ Redis is now running
) else (
    echo ✅ Redis is already running
)

REM ============================================================================
REM PYTHON DEPENDENCIES SETUP
REM ============================================================================

echo.
echo 📦 Installing Python dependencies...
if not exist "scripts\requirements.txt" (
    echo ❌ Requirements file not found at scripts\requirements.txt
    pause
    exit /b 1
)
%PYTHON_CMD% -m pip install -r scripts\requirements.txt
if errorlevel 1 (
    echo ⚠️  Some dependencies may have failed to install.
    echo    Continuing anyway...
)

REM ============================================================================
REM NLP MODEL SETUP
REM ============================================================================

echo.
echo 📚 Setting up NLP models...
echo   - Downloading spaCy model...
%PYTHON_CMD% -m spacy download en_core_web_sm >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  spaCy model download had issues (may already be installed)
) else (
    echo   ✅ spaCy model ready
)

echo   - Downloading NLTK data...
%PYTHON_CMD% -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('wordnet', quiet=True)" >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  NLTK data download had issues (may already be installed)
) else (
    echo   ✅ NLTK data ready
)

REM ============================================================================
REM DIRECTORY SETUP
REM ============================================================================

if not exist "cachedir" mkdir cachedir
echo ✅ Cache directory ready

REM ============================================================================
REM APPLICATION STARTUP
REM ============================================================================

REM Check if honcho is installed
where honcho >nul 2>&1
if errorlevel 1 (
    echo.
    echo ⚠️  honcho is not installed. Installing it now...
    %PYTHON_CMD% -m pip install honcho
)

REM Check if Procfile exists
if not exist "Procfile" (
    echo ❌ Procfile not found. Cannot start application.
    pause
    exit /b 1
)

REM Final Redis connection test
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo ❌ Cannot connect to Redis. Please ensure Redis is running.
    pause
    exit /b 1
)

echo.
echo 🎯 Starting Range Gap Finder application...
echo 🌐 Starting web server and worker processes...
echo.

honcho start

echo.
echo ✅ Range Gap Finder has stopped.
echo.
echo To stop Redis later:
echo   If installed as service: net stop Redis
echo   If running directly: Close the Redis window or press Ctrl+C in that window
pause

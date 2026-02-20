#!/usr/bin/env python3
"""
Range Gap Finder - Cross-Platform Startup Script
Works on both Windows and Mac/Linux
"""

import sys
import subprocess
import os
import platform
import glob
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

def find_python_windows():
    """Find Python on Windows by checking common installation locations"""
    import os
    import glob
    
    # Try Python Launcher (py.exe) first - most reliable on Windows
    if check_command_exists("py"):
        try:
            result = subprocess.run(["py", "--version"], capture_output=True, text=True, check=True)
            if "Python 3" in result.stdout:
                return "py"
        except:
            pass
    
    # Common Python installation locations on Windows
    search_patterns = [
        "C:/Program Files/Python3*/python.exe",
        "C:/Program Files (x86)/Python3*/python.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs/Python/Python3*/python.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "AppData/Local/Programs/Python/Python3*/python.exe"),
        "C:/Python3*/python.exe",
    ]
    
    # Search common installation directories
    for pattern in search_patterns:
        try:
            matches = glob.glob(pattern)
            if matches:
                # Return the first match (usually the latest version)
                return matches[0]
        except:
            continue
    
    return None

def get_python_command():
    """Get the appropriate Python command for the platform"""
    if platform.system() == "Windows":
        # On Windows, try python first (python3 is not standard on Windows)
        # Also try py.exe (Python Launcher) which is most reliable
        for cmd in ["py", "python"]:
            if check_command_exists(cmd):
                # Verify it's actually Python, not the Microsoft Store redirect
                try:
                    result = subprocess.run([cmd, "--version"], capture_output=True, text=True, check=True, timeout=5)
                    if "Python" in result.stdout or "Python" in result.stderr:
                        return cmd
                except:
                    continue
        
        # If not in PATH, search common installation locations
        python_path = find_python_windows()
        if python_path:
            return python_path
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
        print("❌ Python 3 is not installed or not found in PATH.")
        print("")
        if platform.system() == "Windows":
            print("IMPORTANT: Installing the Python extension in VS Code does NOT install Python itself!")
            print("")
            print("⚠️  WINDOWS USERS: Use 'python' NOT 'python3'")
            print("   Windows uses 'python' command, not 'python3'")
            print("   Example: python run.py (NOT python3 run.py)")
            print("")
            print("To install Python:")
            print("  1. Download from: https://www.python.org/downloads/")
            print("  2. Run the installer")
            print("  3. IMPORTANT: Check 'Add Python to PATH' during installation")
            print("  4. Restart your terminal/PowerShell after installation")
            print("  5. Verify with: python --version")
            print("")
            print("NOTE: The Python extension in VS Code is just an editor tool.")
            print("      You need to install Python itself from python.org")
        else:
            print("Please install Python 3.8 or higher.")
        sys.exit(1)
    
    # If Python was found but not in PATH, warn the user
    if platform.system() == "Windows" and ("Program Files" in python_cmd or "AppData" in python_cmd):
        print(f"⚠️  Found Python at: {python_cmd}")
        print("   Python is not in your PATH. Consider adding it to PATH or reinstalling with 'Add Python to PATH' checked.")
        print("")
    
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

def check_redis_installed():
    """Check if Redis is installed locally"""
    if platform.system() == "Windows":
        # On Windows, check for redis-cli or redis-server
        return check_command_exists("redis-cli") or check_command_exists("redis-server")
    else:
        # On Mac/Linux, check for redis-cli or redis-server
        return check_command_exists("redis-cli") or check_command_exists("redis-server")

def check_redis_running():
    """Check if Redis is running"""
    if not check_command_exists("redis-cli"):
        return False
    success, output, _ = run_command("redis-cli ping", check=False)
    return success and "PONG" in output.upper()

def install_redis_windows():
    """Attempt to install Redis on Windows"""
    print("🔧 Redis is not installed. Attempting to install Redis...")
    print("")
    
    # Try Chocolatey first
    if check_command_exists("choco"):
        print("📦 Installing Redis via Chocolatey...")
        success, _, error = run_command("choco install redis-64 -y", shell=True, check=False)
        if success:
            print("✅ Redis installed successfully via Chocolatey")
            return True
        else:
            print(f"⚠️  Chocolatey installation failed: {error}")
    
    # Try winget (Windows Package Manager)
    if check_command_exists("winget"):
        print("📦 Installing Redis via winget...")
        success, _, error = run_command("winget install Redis.Redis", shell=True, check=False)
        if success:
            print("✅ Redis installed successfully via winget")
            return True
        else:
            print(f"⚠️  winget installation failed: {error}")
    
    print("❌ Could not automatically install Redis on Windows.")
    print("")
    print("Please install Redis manually using one of these methods:")
    print("  1. Chocolatey: choco install redis-64")
    print("  2. winget: winget install Redis.Redis")
    print("  3. Download from: https://github.com/microsoftarchive/redis/releases")
    print("  4. Use WSL: Install Redis in Windows Subsystem for Linux")
    print("")
    return False

def start_redis():
    """Start Redis server if not already running"""
    # Check if Redis is already running
    if check_redis_running():
        print("✅ Redis is already running")
        return True
    
    print("🔧 Starting Redis server...")
    
    if platform.system() == "Windows":
        # Windows: Try to start Redis service or run directly
        # Check if Redis is installed as a service
        success, output, _ = run_command("sc query Redis", shell=True, check=False)
        if success and "RUNNING" in output.upper():
            print("✅ Redis service is running")
            return True
        
        # Try to start Redis service
        success, _, _ = run_command("net start Redis", shell=True, check=False)
        if success:
            print("✅ Redis service started")
            # Wait a moment and verify
            import time
            time.sleep(2)
            if check_redis_running():
                return True
        
        # Try to run redis-server directly
        if check_command_exists("redis-server"):
            print("⚠️  Starting Redis directly (not as service)...")
            print("   Note: Redis will run in the foreground. Consider installing as a service.")
            # On Windows, redis-server might need to be run in background
            # For now, just inform the user
            print("   Please start Redis manually: redis-server")
            return False
    else:
        # Mac/Linux: Try different startup methods
        if check_command_exists("brew"):
            success, output, _ = run_command("brew services list", check=False)
            if success and "redis" in output.lower():
                run_command("brew services start redis", check=False)
                import time
                time.sleep(2)
                if check_redis_running():
                    print("✅ Redis started via Homebrew services")
                    return True
        
        if check_command_exists("systemctl"):
            run_command("sudo systemctl start redis", check=False)
            run_command("sudo systemctl start redis-server", check=False)
            import time
            time.sleep(2)
            if check_redis_running():
                print("✅ Redis started via systemd")
                return True
        
        if check_command_exists("service"):
            run_command("sudo service redis start", check=False)
            run_command("sudo service redis-server start", check=False)
            import time
            time.sleep(2)
            if check_redis_running():
                print("✅ Redis started via service command")
                return True
        
        if check_command_exists("redis-server"):
            run_command("redis-server --daemonize yes", check=False)
            import time
            time.sleep(2)
            if check_redis_running():
                print("✅ Redis started directly")
                return True
    
    print("❌ Could not start Redis automatically.")
    print("   Please start Redis manually and run this script again.")
    return False

def setup_redis():
    """Setup Redis - check installation and start if needed"""
    # Check if Redis is installed
    if not check_redis_installed():
        if platform.system() == "Windows":
            if not install_redis_windows():
                sys.exit(1)
        else:
            print("❌ Redis is not installed locally.")
            print("")
            print("Please install Redis using one of these methods:")
            print("  macOS:   brew install redis")
            print("  Ubuntu:  sudo apt-get install redis-server")
            print("  CentOS:  sudo yum install redis")
            print("  Fedora:  sudo dnf install redis")
            print("")
            print("Or visit: https://redis.io/download")
            sys.exit(1)
    
    print("✅ Redis is installed")
    
    # Start Redis if not running
    if not start_redis():
        print("")
        print("⚠️  Redis is not running. Please start Redis and try again.")
        sys.exit(1)
    
    # Final verification
    if not check_redis_running():
        print("❌ Cannot connect to Redis. Please ensure Redis is running on localhost:6379")
        sys.exit(1)

def install_dependencies(python_cmd):
    """Install Python dependencies"""
    # On Windows, prefer requirements-windows.txt if it exists (excludes hdbscan)
    if platform.system() == "Windows":
        windows_req = Path("scripts/requirements-windows.txt")
        if windows_req.exists():
            requirements_file = windows_req
            print("📦 Installing Python dependencies (Windows-optimized)...")
        else:
            requirements_file = Path("scripts/requirements.txt")
            print("📦 Installing Python dependencies...")
    else:
        requirements_file = Path("scripts/requirements.txt")
        print("📦 Installing Python dependencies...")
    
    if not requirements_file.exists():
        print("⚠️  Warning: Requirements file not found. Skipping dependency installation.")
        return
    
    # On Windows, hdbscan requires C++ build tools. Install it separately with better error handling
    if platform.system() == "Windows" and requirements_file.name == "requirements.txt":
        # Read requirements and install hdbscan separately if it fails
        try:
            with open(requirements_file, 'r') as f:
                requirements = f.read().splitlines()
            
            # Install all packages except hdbscan first
            other_packages = [pkg for pkg in requirements if 'hdbscan' not in pkg.lower()]
            temp_req = Path("scripts/requirements_temp.txt")
            with open(temp_req, 'w') as f:
                f.write('\n'.join(other_packages))
            
            # Install other packages
            success, _, error = run_command([python_cmd, "-m", "pip", "install", "-r", str(temp_req)], check=False)
            temp_req.unlink()  # Clean up temp file
            
            # Try to install hdbscan separately
            print("  Attempting to install hdbscan (may require C++ build tools)...")
            hdbscan_success, _, hdbscan_error = run_command([python_cmd, "-m", "pip", "install", "hdbscan"], check=False)
            
            if not hdbscan_success:
                print("⚠️  Warning: hdbscan failed to install (requires Microsoft C++ Build Tools)")
                print("   The application may work without it, but some clustering features may be unavailable.")
                print("   To install C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/")
                print("   Or try: pip install hdbscan --only-binary :all:")
            
        except Exception as e:
            print(f"⚠️  Error processing requirements: {e}")
            # Fall back to normal installation
            success, _, error = run_command([python_cmd, "-m", "pip", "install", "-r", str(requirements_file)], check=False)
    else:
        # On Mac/Linux, install normally
        success, _, error = run_command([python_cmd, "-m", "pip", "install", "-r", str(requirements_file)], check=False)
    
    if not success:
        print(f"⚠️  Warning: Some dependencies may have failed to install")
        print("   The application may still work, but some features might be unavailable.")

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
    python_cmd = get_python_command()
    
    if not check_command_exists("honcho"):
        print("⚠️  Honcho is not installed. Installing...")
        success, _, error = run_command([python_cmd, "-m", "pip", "install", "honcho"], check=False)
        if not success:
            print("❌ Failed to install honcho.")
            print(f"   Error: {error}")
            print("   Please install manually: pip install honcho")
            sys.exit(1)
        
        # Verify honcho is now available
        if not check_command_exists("honcho"):
            print("❌ Honcho installation completed but command not found.")
            print("   Please restart your terminal and try again.")
            print("   Or install manually: pip install honcho")
            sys.exit(1)
    
    print("🎯 Starting Range Gap Finder application...")
    print("🌐 Starting web server and worker processes...")
    print("")
    print("✅ Range Gap Finder is now running!")
    print("🌍 Open your browser and go to: http://localhost:5000")
    print("")
    print("To stop the application, press Ctrl+C")
    if platform.system() == "Windows":
        print("To stop Redis: net stop Redis (if installed as service)")
    else:
        print("To stop Redis: brew services stop redis (macOS) or sudo systemctl stop redis (Linux)")
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
    
    # Windows-specific note
    if platform.system() == "Windows":
        print("")
        print("💡 TIP: On Windows, use 'python' not 'python3'")
        print("   If you see 'Python was not found' errors, try: python run.py")
    
    print("")
    
    # Check Python
    python_cmd = check_python_version()
    
    # Setup Redis (install if needed, start if not running)
    setup_redis()
    
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


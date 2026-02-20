# Windows Troubleshooting Guide

## Issue: "Docker is running" message

**Problem**: You see messages like "✅ Docker is running" and "🔧 Starting Redis container..."

**Cause**: You're running an old version of `run.py` that still uses Docker.

**Solution**: 
1. Make sure you have the latest version of `run.py` from the repository
2. The updated version does NOT use Docker - it installs Redis locally
3. If you still see Docker messages, delete any cached `.pyc` files:
   ```powershell
   Remove-Item -Recurse -Force __pycache__
   ```

## Issue: hdbscan build error

**Error**: 
```
error: Microsoft Visual C++ 14.0 or greater is required.
```

**Solutions**:

### Option 1: Install C++ Build Tools (Recommended)
1. Download Microsoft C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Run the installer
3. Select "Desktop development with C++" workload
4. Install and restart your terminal
5. Run the script again

### Option 2: Use Pre-built Wheel (If Available)
```powershell
pip install hdbscan --only-binary :all:
```

### Option 3: Skip hdbscan (Application Still Works)
- The script will continue without hdbscan
- Most features will work fine
- Clustering features may be unavailable
- You can install it later if needed

## Issue: honcho not found

**Error**: 
```
FileNotFoundError: [WinError 2] The system cannot find the file specified
```

**Solution**:
```powershell
pip install honcho
```

Then restart your terminal and try again.

## Issue: Python 3.14 detected but packages fail

**Problem**: Python 3.14 is very new and some packages may not have wheels available yet.

**Solutions**:
1. **Use Python 3.11 or 3.12** (more stable):
   - Download from: https://www.python.org/downloads/
   - These versions have better package compatibility

2. **Or continue with 3.14**:
   - The script will try to install packages
   - Some may fail but the application should still work

## Quick Fix Checklist

If you're having issues, try these in order:

1. ✅ Make sure you're using `python` not `python3`
2. ✅ Verify Python is installed: `python --version`
3. ✅ Update pip: `python -m pip install --upgrade pip`
4. ✅ Install honcho manually: `pip install honcho`
5. ✅ Install C++ Build Tools if you need hdbscan
6. ✅ Make sure you have the latest `run.py` (no Docker references)

## Still Having Issues?

1. Check the main README.md troubleshooting section
2. Check WINDOWS_SETUP.md for Windows-specific instructions
3. Make sure Redis is installed and running: `redis-cli ping` should return "PONG"

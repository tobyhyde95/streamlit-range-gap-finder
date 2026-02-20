# Windows Setup Guide

## Quick Start for Windows Users

### ⚠️ Important: Use `python` NOT `python3` on Windows!

Windows uses the `python` command, not `python3`. If you see this error:
```
Python was not found; run without arguments to install from the Microsoft Store
```

**Solution**: Use `python` instead of `python3`

### Step-by-Step Instructions

1. **Install Python** (if not already installed):
   - Download from: https://www.python.org/downloads/
   - Run the installer
   - ✅ **IMPORTANT**: Check "Add Python to PATH" during installation
   - Restart PowerShell/CMD after installation

2. **Verify Python Installation**:
   ```powershell
   python --version
   ```
   You should see something like: `Python 3.x.x`
   
   ⚠️ If you get an error with `python3`, that's normal - use `python` instead!

3. **Run the Application**:
   ```powershell
   # Option 1: Use Python directly (recommended)
   python run.py
   
   # Option 2: Use the batch file
   run.bat
   
   # Option 3: Use PowerShell script
   powershell -ExecutionPolicy Bypass -File run.ps1
   ```

### Common Issues

**"Python was not found; run without arguments to install from the Microsoft Store"**
- **Cause**: You used `python3` instead of `python`
- **Solution**: Use `python run.py` (without the "3")

**"Python was not found" (even with `python`)**
- Python is not installed or not in PATH
- **Solution**: 
  1. Install Python from https://www.python.org/downloads/
  2. Make sure to check "Add Python to PATH" during installation
  3. Restart your terminal

**"Installing the Python extension in VS Code does NOT install Python itself!"**
- VS Code Python extension is just an editor tool
- You need to install Python separately from python.org

**"hdbscan" build error - "Microsoft Visual C++ 14.0 or greater is required"**
- **Cause**: The `hdbscan` package needs C++ build tools to compile
- **Solutions**:
  1. **Install C++ Build Tools** (for full functionality):
     - Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/
     - Install "Desktop development with C++" workload
     - Restart terminal and try again
  2. **Skip hdbscan** (most features still work):
     - The script will continue without it
     - Install manually later if needed: `pip install hdbscan`

**"honcho" not found error**
- **Solution**: Install honcho manually:
  ```powershell
  pip install honcho
  ```
  Then restart your terminal and run the script again

### Command Reference

| Command | Windows | Mac/Linux |
|---------|---------|-----------|
| Check version | `python --version` | `python3 --version` |
| Run script | `python run.py` | `python3 run.py` |
| Install package | `python -m pip install` | `python3 -m pip install` |

### Need Help?

If you're still having issues:
1. Make sure Python is installed: https://www.python.org/downloads/
2. Verify it's in PATH: `python --version` should work
3. Try using `py` command: `py run.py` (Python Launcher)
4. Check the main README.md for more troubleshooting tips

# Range Gap Finder - SEO Competitor & Gap Analyzer

A comprehensive web application for advanced SEO analysis, designed to identify content gaps, competitive opportunities, and market share insights from your SEO data exports.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ (with pip)
- Redis (will be installed automatically if not present)
- Git

### Running the Application

1. **Clone and navigate to the project:**
   ```bash
   cd range_gap_finder
   ```

2. **Start the application:**

   **On Mac/Linux:**
   ```bash
   # Option 1: Use the Python launcher (recommended - works on both platforms)
   python3 run.py
   
   # Option 2: Use the bash script
   ./run.sh
   ```

   **On Windows:**
   ```powershell
   # Option 1: Use the Python launcher (recommended - works on both platforms)
   python run.py
   
   # Option 2: Use the batch file (double-click or run in CMD)
   run.bat
   
   # Option 3: Use PowerShell script
   powershell -ExecutionPolicy Bypass -File run.ps1
   ```
   
   **Important for Windows users:**
   - ⚠️ **Use `python` NOT `python3`** - Windows uses `python` command
   - If you see "Python was not found" when using `python3`, try `python` instead
   - Make sure Python is added to your PATH during installation
   - If you see "Python was not found", install Python from https://www.python.org/downloads/
   - Redis will be automatically installed via Chocolatey or winget if available
   - If automatic Redis installation fails, see the troubleshooting section below
   - 📖 **See WINDOWS_SETUP.md for detailed Windows instructions**

3. **Access the frontend:**
   Open your browser and go to: **http://localhost:5000**

   The application will automatically serve the main interface at this URL.

## 📋 What the Application Does

This tool analyzes your SEO data exports to provide:

- **Content Gaps**: Keywords where competitors rank but you don't
- **Competitive Opportunities**: Keywords where competitors outrank you
- **Market Share Analysis**: Traffic distribution between domains
- **Taxonomy & Architecture Analysis**: Category and facet structure insights

## 🔧 Application Architecture

- **Frontend**: Modern web interface with interactive tables and filtering
- **Backend**: Flask API with Celery for background processing
- **Database**: Redis for task queue management (runs locally, no Docker required)
- **Processing**: Asynchronous analysis with real-time progress updates

## 📁 Project Structure

```
range_gap_finder/
├── assets/                 # Frontend assets (CSS, JS)
├── seo_analyzer/          # Python backend code
├── scripts/               # Startup scripts
├── range-gap-finder.html  # Main frontend interface
├── run.py                 # Cross-platform Python launcher (recommended)
├── run.sh                 # Mac/Linux bash script
├── run.bat                # Windows batch script
├── run.ps1                # Windows PowerShell script
├── Procfile              # Process configuration
└── README.md             # This file
```

## 🎯 How to Use

1. **Upload Data**: Upload your domain's SEO export and competitor exports
2. **Map Columns**: Automatically map or manually configure column mappings
3. **Configure Analysis**: Select which analysis types to run
4. **Run Analysis**: Submit and monitor progress in real-time
5. **Explore Results**: Use the interactive interface to explore insights

## 🔍 Available Analysis Types

- **Content Gaps** (Individual Keywords & Topic Groups)
- **Competitive Opportunities** (Individual Keywords & Topic Groups)  
- **Market Share Analysis** (Individual Keywords & Topic Groups)
- **Taxonomy & Architecture Analysis** (Category Overhaul Matrix & Facet Potential)

## 🛠️ Development

For development setup and Git workflow instructions, see `scripts/README.md`.

## 📞 Support & Troubleshooting

### Common Issues

**"Python was not found" (Windows)**
- **Common cause**: Installing the Python extension in VS Code does NOT install Python itself!
- The VS Code Python extension is just an editor tool - you need to install Python separately
- **Solution**: 
  1. Download Python from https://www.python.org/downloads/ (NOT from VS Code extensions)
  2. Run the Python installer (.exe file)
  3. **IMPORTANT**: During installation, check "Add Python to PATH" checkbox
  4. Restart your terminal/PowerShell after installation
  5. Verify with: `python --version` (NOT `python3` on Windows!)
  
- **"Python was not found; run without arguments to install from the Microsoft Store"**:
  - This happens when you use `python3` on Windows - Windows doesn't recognize `python3`
  - **Solution**: Use `python` instead of `python3` on Windows
  - Example: `python run.py` (NOT `python3 run.py`)
  
- **If Python is installed but not found**:
  - The scripts will try to find Python in common locations automatically
  - To fix permanently: Add Python to your Windows PATH environment variable
  - Or reinstall Python and make sure to check "Add Python to PATH"

**"Redis is not installed"**
- The script will attempt to install Redis automatically
- **Windows**: Requires Chocolatey (`choco`) or winget
  - Install Chocolatey: https://chocolatey.org/install
  - Or use winget (built into Windows 10/11)
  - Manual option: Download Redis from https://github.com/microsoftarchive/redis/releases
- **Mac/Linux**: Uses Homebrew, apt-get, yum, or dnf automatically

**"Cannot connect to Redis"**
- Redis is not running
- **Windows**: 
  - If installed as service: `net start Redis`
  - If running directly: Start `redis-server.exe` manually
- **Mac**: `brew services start redis`
- **Linux**: `sudo systemctl start redis` or `sudo service redis start`

**Port 5000 already in use**
- Another application is using port 5000
- **Solution**: Stop the other application or change the port in `Procfile`

**"hdbscan" build error on Windows**
- Error: "Microsoft Visual C++ 14.0 or greater is required"
- **Cause**: `hdbscan` requires C++ build tools to compile on Windows
- **Solutions**:
  1. **Install C++ Build Tools** (recommended for full functionality):
     - Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
     - Install "Desktop development with C++" workload
     - Restart terminal and run the script again
  2. **Use pre-built wheel** (if available):
     ```powershell
     pip install hdbscan --only-binary :all:
     ```
  3. **Skip hdbscan** (application will work but clustering features may be unavailable):
     - The script will continue without hdbscan
     - Most features will still work fine

**"honcho" not found error**
- Error: `FileNotFoundError: [WinError 2] The system cannot find the file specified`
- **Cause**: honcho installation failed or command not in PATH
- **Solution**:
  ```powershell
  pip install honcho
  ```
  Then restart your terminal and try again

### Checking Status

1. **Check Redis is running:**
   - **All platforms**: `redis-cli ping` (should return "PONG")
   
2. **Check application is running:**
   - Open http://localhost:5000 in your browser
   
3. **Check terminal logs:**
   - Look for error messages in the terminal where you ran the script

## 🌐 Cross-Platform Support

This application works seamlessly on **Windows**, **macOS**, and **Linux** without requiring Docker. The recommended way to start the application is using `run.py`, which automatically detects your platform and runs the appropriate commands.

**Why use `run.py`?**
- ✅ Works on Windows, macOS, and Linux
- ✅ Automatic platform detection
- ✅ Automatic Redis installation and setup
- ✅ Better error handling
- ✅ Consistent experience across platforms
- ✅ No Docker required - everything runs locally

---

**Note**: The application requires CSV exports from SEO tools (like Ahrefs, SEMrush, etc.) with keyword, URL, position, and traffic data.

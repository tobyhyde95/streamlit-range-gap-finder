# Docker vs Local Mode Guide

## Quick Comparison

| Feature | Local Mode | Docker Mode |
|---------|-----------|-------------|
| **Docker Required** | ❌ No | ✅ Yes |
| **Redis Installation** | Automatic (local) | Container |
| **Setup Complexity** | Medium | Easy |
| **Resource Usage** | Lower | Higher |
| **Isolation** | System service | Container |
| **Cleanup** | Manual | `docker stop redis-cache` |
| **Platform Support** | All | All (with Docker) |

## Auto Mode (Default)

### How It Works
1. Script checks if Docker Desktop is available
2. If Docker is available → uses Docker mode
3. If Docker is not available → automatically uses local mode
4. No user intervention needed!

### Advantages
- ✅ Smart automatic selection
- ✅ Uses Docker when available (easier)
- ✅ Falls back to local when Docker unavailable
- ✅ No configuration needed

### Usage
```bash
# Default (auto mode - tries Docker first)
python run.py
```

## Local Mode

### Advantages
- ✅ No Docker installation needed
- ✅ Lower resource usage
- ✅ Redis persists as system service
- ✅ Works everywhere Python works

### Disadvantages
- ⚠️ Requires Redis installation (handled automatically)
- ⚠️ Redis runs as system service

### Usage
```bash
# Force local mode (skip Docker check)
python run.py --local
```

### What Happens
1. Script checks if Redis is installed locally
2. If not installed, automatically installs Redis (Homebrew, apt-get, Chocolatey, etc.)
3. Starts Redis as local service
4. Runs application connecting to local Redis

### Stopping Redis
```bash
# macOS
brew services stop redis

# Linux
sudo systemctl stop redis

# Windows
net stop Redis
```

## Docker Mode

### Advantages
- ✅ Isolated Redis container
- ✅ Easy cleanup (just stop container)
- ✅ Consistent across platforms
- ✅ No local Redis installation needed

### Disadvantages
- ⚠️ Requires Docker Desktop
- ⚠️ Higher resource usage
- ⚠️ Container must be running

### Usage
```bash
# Force Docker mode (requires Docker Desktop)
python run.py --docker

# Or just run normally - will auto-select Docker if available
python run.py
```

### Prerequisites
1. Install Docker Desktop: https://www.docker.com/products/docker-desktop
2. Start Docker Desktop
3. Verify: `docker info` should work

### What Happens
1. Script checks if Docker is running
2. Creates/starts Redis container (`redis-cache`)
3. Runs application connecting to containerized Redis

### Stopping Redis
```bash
# Stop container
docker stop redis-cache

# Or using docker-compose
docker-compose stop redis

# Remove container (optional)
docker rm redis-cache
```

## Switching Between Modes

### From Docker to Local
1. Stop Docker container: `docker stop redis-cache`
2. Run: `python run.py --local`
3. Script will install Redis locally if needed

### From Local to Docker
1. Stop local Redis (see commands above)
2. Ensure Docker Desktop is running
3. Run: `python run.py --docker`

## Troubleshooting

### Docker Mode Issues

**"Docker is not running"**
- Start Docker Desktop
- Wait for it to fully start (whale icon in system tray)
- Verify with: `docker info`

**"Cannot connect to Redis"**
- Check container is running: `docker ps`
- Check logs: `docker logs redis-cache`
- Restart container: `docker restart redis-cache`

### Local Mode Issues

**"Redis installation failed"**
- See main README troubleshooting section
- Try manual installation
- Or switch to Docker mode: `python run.py --docker`

**"Cannot connect to Redis"**
- Check Redis is running: `redis-cli ping`
- Start Redis manually (see commands above)
- Check Redis logs

## Recommendation

**Just run `python run.py`** - the script will automatically:
- Use Docker if available (easier, cleaner)
- Use local mode if Docker unavailable (still works!)

**Force a specific mode only if:**
- You want to ensure Docker is used: `python run.py --docker`
- You want to ensure local mode: `python run.py --local`
- You're troubleshooting and need to test a specific mode

## Smart Defaults!

The default behavior tries Docker first (easier) and falls back to local (more compatible). Both modes provide the same functionality - the script chooses the best option for your environment automatically!

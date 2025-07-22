# ./start.sh
#!/bin/bash
echo "--- Starting SEO Analyzer Application (Web & Worker) ---"

# Activate the Python virtual environment
source venv/bin/activate

# Ensure Redis is running via Docker
if [ ! "$(docker ps -q -f name=redis)" ]; then
    if [ "$(docker ps -aq -f status=exited -f name=redis)" ]; then
        # cleanup
        docker rm redis
    fi
    # run
    echo "Starting Redis container..."
    docker run -d --name redis -p 6379:6379 redis
else
    echo "Redis container is already running."
fi

# Start all processes defined in the Procfile
honcho start
#!/bin/bash

# Names of the containers to log
CONTAINERS=("security-management-backend-1" "security-management-worker-1")

echo "========================================"
echo "Streaming logs for:"
for c in "${CONTAINERS[@]}"; do
  echo " - $c"
done
echo "========================================"
echo "Press Ctrl+C to stop."
echo ""

# Function to kill background jobs on exit
cleanup() {
    echo ""
    echo "Stopping log streams..."
    kill $(jobs -p) 2>/dev/null
}
trap cleanup EXIT

# Start tailing logs in background
for container in "${CONTAINERS[@]}"; do
    # Check if container exists/is running
    if docker ps -q -f name="$container" > /dev/null; then
        # Colorize output prefix if possible, or just print
        (docker logs -f --tail 50 "$container" | sed "s/^/[${container}] /") &
    else
        echo "Warning: Container '$container' not found or not running."
    fi
done

# Wait for all background jobs
wait

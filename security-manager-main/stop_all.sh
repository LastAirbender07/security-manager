#!/bin/bash
set -e

echo "========================================"
echo "Stopping & Wiping Security Management Stack"
echo "========================================"

# Get the absolute path of the script directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Clean Frontend
echo ">>> [1/2] Wiping Frontend..."
cd "$PROJECT_ROOT/frontend"
echo "Cleaning Frontend containers, volumes, and images..."
docker-compose down -v --rmi all 2>/dev/null || true

# Clean Backend
echo ""
echo ">>> [2/2] Wiping Backend..."
cd "$PROJECT_ROOT/backend"
echo "Cleaning Backend containers, volumes, images, and network..."
docker-compose down -v --rmi all 2>/dev/null || true


echo ""
echo "========================================"
echo "Stack Wipe Complete!"
echo "========================================"

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
echo "Cleaning Backend containers, volumes, images, and network..."
docker rm -f security-management-db-1 security-management-broker-1 security-management-backend-1 security-management-worker-1 2>/dev/null || true
docker volume rm guardian-db-data zap-data zap-data-vol 2>/dev/null || true
docker rmi guardian-backend 2>/dev/null || true
docker network rm backend_guardian-net 2>/dev/null || true

echo ""
echo "========================================"
echo "Stack Wipe Complete!"
echo "========================================"

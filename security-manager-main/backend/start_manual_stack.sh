#!/bin/bash
set -e

echo "Cleaning up..."
docker rm -f security-management-db-1 security-management-broker-1 security-management-backend-1 security-management-worker-1 || true

echo "Ensuring network..."
docker network create backend_guardian-net || true

echo "Starting DB..."
docker run -d --name security-management-db-1 \
  --network backend_guardian-net \
  -e POSTGRES_USER=guardian \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=security_guardian \
  -v guardian-db-data:/var/lib/postgresql/data \
  postgres:15-alpine

echo "Starting Broker..."
docker run -d --name security-management-broker-1 \
  --network backend_guardian-net \
  redis:7-alpine

echo "Building Backend/Worker Image from scratch..."
docker build --no-cache -t guardian-backend .

echo "Starting Backend..."
docker run -d --name security-management-backend-1 \
  --network backend_guardian-net \
  -p 8000:8000 \
  -v $(pwd):/app \
  --env-file .env \
  -e DATABASE_URL=postgres://guardian:password@security-management-db-1:5432/security_guardian \
  -e REDIS_URL=redis://security-management-broker-1:6379/0 \
  -e PYTHONPATH=/app \
  guardian-backend \
  bash -c "aerich upgrade || aerich init-db && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo "Starting Worker..."
docker run -d --name security-management-worker-1 \
  --network backend_guardian-net \
  -v $(pwd):/app \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v zap-data:/zap-data \
  --env-file .env \
  -e HOST_WORK_DIR=$(pwd) \
  -e DATABASE_URL=postgres://guardian:password@security-management-db-1:5432/security_guardian \
  -e REDIS_URL=redis://security-management-broker-1:6379/0 \
  -e PYTHONPATH=/app \
  -e ZAP_VOLUME_NAME=zap-data-vol \
  guardian-backend \
  celery -A worker.celery_app worker --loglevel=info

echo "Stack started successfully."

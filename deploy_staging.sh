#!/bin/bash

set -e

IMAGE_NAME="bookslot-app-staging"

echo "--- Building Docker image ---"
docker build -t $IMAGE_NAME .

echo "--- Stopping and removing existing container (if any) ---"
docker stop $IMAGE_NAME || true
docker rm $IMAGE_NAME || true

echo "--- Running Docker container in detached mode ---"
docker run -d --name $IMAGE_NAME --env-file .env -p 8000:8000 $IMAGE_NAME

echo "--- Waiting for the application to start (optional, adjust as needed) ---"
sleep 10

echo "--- Running tests inside the Docker container ---"
docker exec $IMAGE_NAME bash -c "pytest"

echo "--- Deployment and testing complete ---"
echo "Application should be running on http://localhost:8000"

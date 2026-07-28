#!/bin/bash
set -e
echo "Starting deployment to staging environment..."
IMAGE_TAG="bookslot-app-staging:$(date +%Y%m%d%H%M%S)"
docker build -t $IMAGE_TAG .
echo "Docker image $IMAGE_TAG built successfully."
CONTAINER_NAME="bookslot-staging"
echo "Stopping and removing existing container (if any): $CONTAINER_NAME..."
docker stop $CONTAINER_NAME || true
docker rm $CONTAINER_NAME || true
echo "Existing container stopped and removed."
echo "Running new container: $CONTAINER_NAME..."
if [ ! -f .env ]; then
    echo "Warning: .env file not found. Using environment variables directly or default values."
    echo "Please create a .env file or set environment variables before running in production."
else
    echo "Loading environment variables from .env file..."
    ENV_VARS=$(cat .env | grep -v '^#' | xargs -I {} echo -e "-e {}")
    docker run -d --name $CONTAINER_NAME -p 80:8000 $ENV_VARS $IMAGE_TAG
fi
echo "New container $CONTAINER_NAME started successfully on port 80."
echo "Deployment to staging complete. Application should be accessible at http://localhost (or your staging domain)."
echo "Next step: Perform User Acceptance Testing (UAT)."
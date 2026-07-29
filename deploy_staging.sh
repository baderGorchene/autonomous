#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting Staging Deployment ---"

# Define variables
APP_NAME="bookslot-staging"
DOCKER_IMAGE_NAME="bookslot-app-staging"
DOCKER_REGISTRY="your-docker-registry.com" # Replace with your Docker registry, e.g., ghcr.io/your-username
ENV_FILE=".env.staging" # Assuming a separate .env file for staging

# Ensure .env.staging exists
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: Staging environment file '$ENV_FILE' not found."
  echo "Please create it with necessary environment variables."
  exit 1
fi

echo "Building Docker image..."
docker build -t $DOCKER_IMAGE_NAME .

# Tag the image for your registry if you are pushing
# docker tag $DOCKER_IMAGE_NAME $DOCKER_REGISTRY/$DOCKER_IMAGE_NAME:latest

# Push the image to your registry if applicable
# echo "Pushing Docker image to registry..."
# docker push $DOCKER_REGISTRY/$DOCKER_IMAGE_NAME:latest

echo "Stopping and removing any existing container for $APP_NAME..."
docker stop $APP_NAME || true
docker rm $APP_NAME || true

echo "Running new container for $APP_NAME..."
docker run -d \
  --name $APP_NAME \
  --env-file $ENV_FILE \
  -p 80:8000 \
  $DOCKER_IMAGE_NAME:latest

echo "--- Staging Deployment Complete ---"
echo "Application should now be running on port 80."
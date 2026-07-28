#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Load environment variables from .env file (if it exists)
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

# Ensure all required environment variables are set
REQUIRED_ENVS=("SECRET_KEY" "SENDGRID_API_KEY" "TWILIO_ACCOUNT_SID" "TWILIO_AUTH_TOKEN" "TWILIO_WHATSAPP_NUMBER" "DATABASE_URL")

for var in "${REQUIRED_ENVS[@]}"; do
  if [ -z "${!var}" ]; then
    echo "Error: Environment variable $var is not set."
    echo "Please create a .env file or set it in your environment."
    exit 1
  fi
done

# Define image name
IMAGE_NAME="bookslot-staging"

# Build the Docker image
echo "Building Docker image: $IMAGE_NAME"
docker build -t $IMAGE_NAME .

echo "Stopping and removing existing container (if any)"
docker stop $IMAGE_NAME || true
docker rm $IMAGE_NAME || true

echo "Running Docker container: $IMAGE_NAME"
docker run -d \
  --name $IMAGE_NAME \
  -p 8000:8000 \
  -e SECRET_KEY="${SECRET_KEY}" \
  -e SENDGRID_API_KEY="${SENDGRID_API_KEY}" \
  -e TWILIO_ACCOUNT_SID="${TWILIO_ACCOUNT_SID}" \
  -e TWILIO_AUTH_TOKEN="${TWILIO_AUTH_TOKEN}" \
  -e TWILIO_WHATSAPP_NUMBER="${TWILIO_WHATSAPP_NUMBER}" \
  -e DATABASE_URL="${DATABASE_URL}" \
  -e GEMINI_API_KEY="${GEMINI_API_KEY}" \
  $IMAGE_NAME

echo "BookSlot staging environment deployed and running on http://localhost:8000"
echo "Check logs with: docker logs $IMAGE_NAME"
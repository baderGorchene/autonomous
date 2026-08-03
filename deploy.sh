#!/bin/bash

# This is a basic deployment script for BookSlot using Docker.
# For production, consider more robust solutions like Docker Compose, Kubernetes, or cloud-specific CI/CD pipelines.

# --- Configuration --- 
# Set these environment variables in your CI/CD system or local shell before running this script.
# export BOOKSLOT_SECRET_KEY="your-production-secret-key"
# export BOOKSLOT_SENDGRID_API_KEY="your_sendgrid_api_key"
# export BOOKSLOT_TWILIO_ACCOUNT_SID="your_twilio_account_sid"
# export BOOKSLOT_TWILIO_AUTH_TOKEN="your_twilio_auth_token"
# export BOOKSLOT_TWILIO_WHATSAPP_NUMBER="+1XXXXXXXXXX" # Your Twilio WhatsApp enabled number
# export BOOKSLOT_DATABASE_URL="postgresql://user:password@host:port/dbname" # PostgreSQL for production

APP_NAME="bookslot-app"
CONTAINER_NAME="bookslot-instance"
PORT=8000 # Internal container port
HOST_PORT=80 # Port on the host machine to map to the container

echo "--- Stopping and removing existing container (if any) ---"
docker stop ${CONTAINER_NAME} || true
docker rm ${CONTAINER_NAME} || true

echo "--- Building Docker image ---"
docker build -t ${APP_NAME} .

if [ $? -ne 0 ]; then
    echo "Docker build failed! Exiting."
    exit 1
fi

echo "--- Running new Docker container ---"
docker run -d -p ${HOST_PORT}:${PORT} --name ${CONTAINER_NAME} \
    -e SECRET_KEY="${BOOKSLOT_SECRET_KEY}" \
    -e SENDGRID_API_KEY="${BOOKSLOT_SENDGRID_API_KEY}" \
    -e TWILIO_ACCOUNT_SID="${BOOKSLOT_TWILIO_ACCOUNT_SID}" \
    -e TWILIO_AUTH_TOKEN="${BOOKSLOT_TWILIO_AUTH_TOKEN}" \
    -e TWILIO_WHATSAPP_NUMBER="${BOOKSLOT_TWILIO_WHATSAPP_NUMBER}" \
    -e DATABASE_URL="${BOOKSLOT_DATABASE_URL}" \
    ${APP_NAME}

if [ $? -ne 0 ]; then
    echo "Docker run failed! Exiting."
    exit 1
fi

echo "--- BookSlot deployed successfully! ---"
echo "Access the application at http://localhost:${HOST_PORT} (or your server's IP)"

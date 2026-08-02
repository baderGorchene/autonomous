#!/bin/bash
IMAGE_NAME="bookslot-app"
TAG="staging-$(date +%Y%m%d%H%M%S)"
DOCKER_REGISTRY="your-docker-registry" 
FULL_IMAGE_NAME="${DOCKER_REGISTRY}/${IMAGE_NAME}:${TAG}
echo "Verifying staging environment variables..."
if [ -z "$DATABASE_URL" ] || [ -z "$SECRET_KEY" ] || [ -z "$SENDGRID_API_KEY" ]; then
  echo "Error: Missing critical environment variables for staging deployment."
  echo "Please set DATABASE_URL, SECRET_KEY, SENDGRID_API_KEY, etc."
  exit 1
fi
echo "Building Docker image: ${FULL_IMAGE_NAME}"
docker build -t "${FULL_IMAGE_NAME}" .
if [ $? -ne 0 ]; then
  echo "Docker build failed."
  exit 1
fi
echo "Logging in to Docker registry..."
echo "Pushing Docker image to registry..."
docker push "${FULL_IMAGE_NAME}"
if [ $? -ne 0 ]; then
  echo "Docker push failed."
  exit 1
fi
echo "Deployment to staging environment (simulated):"
echo "Image ${FULL_IMAGE_NAME} pushed successfully."
echo "Next steps would involve updating your staging environment (e.g., Kubernetes deployment, Docker Compose, AWS ECS) to pull and run this new image."
echo "Example command to run locally (for testing the image):"
echo "docker run -d -p 8000:8000 --name bookslot-staging \"
echo "  -e DATABASE_URL=\"$DATABASE_URL\" \"
echo "  -e SECRET_KEY=\"$SECRET_KEY\" \"
echo "  -e SENDGRID_API_KEY=\"$SENDGRID_API_KEY\" \"
echo "  -e TWILIO_ACCOUNT_SID=\"$TWILIO_ACCOUNT_SID\" \"
echo "  -e TWILIO_AUTH_TOKEN=\"$TWILIO_AUTH_TOKEN\" \"
echo "  -e TWILIO_WHATSAPP_NUMBER=\"$TWILIO_WHATSAPP_NUMBER\" \"
echo "  -e GEMINI_API_KEY=\"$GEMINI_API_KEY\" \"
echo "  ${FULL_IMAGE_NAME}"
echo "Staging deployment process complete (simulated)."
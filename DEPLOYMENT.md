# BookSlot - Deployment Guide

This document outlines the steps to deploy the BookSlot application to a production environment.

## Overview

The BookSlot application is built with FastAPI and is designed to be containerized using Docker. For production, it is highly recommended to use a robust database like PostgreSQL and to secure your application behind a reverse proxy (e.g., Nginx) or a managed load balancer.

## Prerequisites

*   A server or virtual machine (e.g., AWS EC2, DigitalOcean Droplet, GCP Compute Engine).
*   Docker and Docker Compose installed on your server.
*   A domain name configured to point to your server's IP address.
*   A PostgreSQL database instance (either self-hosted or managed service like AWS RDS, Azure Database for PostgreSQL, Google Cloud SQL).
*   Accounts for SendGrid (email) and Twilio (WhatsApp) with API keys and configured numbers.

## Environment Variables for Production

Ensure your production environment variables are securely set. **Do not commit sensitive information to version control.**

Create a `.env` file on your production server (or use your cloud provider's secret management system) with the following variables:

```ini
# Critical Security Settings
SECRET_KEY="YOUR_VERY_LONG_AND_COMPLEX_SECRET_KEY_FOR_PRODUCTION"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30 # Adjust as needed

# Database Configuration (PostgreSQL Recommended)
DATABASE_URL="postgresql://user:password@host:port/dbname"

# Notification Service Credentials
SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY"
TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID"
TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1XXXXXXXXXX" # Your Twilio WhatsApp number (e.g., whatsapp:+1234567890)

# Optional: Gemini API Key if used for future features
GEMINI_API_KEY=""

# Set to False for production
TESTING=False
```
**Important:** Generate a strong, unique `SECRET_KEY` for your production environment.

## Building the Docker Image

From the root of your project directory, build the Docker image:

```bash
docker build -t bookslot-app:latest .
```

## Running with Docker Compose (Example)

A `docker-compose.yml` file can simplify running your application along with other services like a reverse proxy.

Here's an example `docker-compose.yml` structure (you'll need to adapt it for your specific setup):

```yaml
version: '3.8'

services:
  app:
    image: bookslot-app:latest
    container_name: bookslot_app
    env_file:
      - ./.env # Make sure this file is present on your server
    ports:
      - "8000:8000" # Expose app on port 8000, typically behind a reverse proxy
    depends_on:
      - db # If using a database service in the same compose file
    restart: always

  db: # Example PostgreSQL service (for local testing/small deployments, use managed DB in production)
    image: postgres:13-alpine
    container_name: bookslot_db
    environment:
      POSTGRES_DB: ${DB_NAME:-bookslot_db}
      POSTGRES_USER: ${DB_USER:-bookslot_user}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-bookslot_password}
    volumes:
      - db_data:/var/lib/postgresql/data
    restart: always

volumes:
  db_data: # For persistent database storage
```

To run your application using Docker Compose:

```bash
docker-compose up -d
```

### Database Initialization

When deploying for the first time with a new database, you need to run the migrations (or `create_tables()` function) to set up the schema.

You can do this by executing a command inside your running Docker container:

```bash
docker exec -it bookslot_app python -c "from src.database import create_tables; create_tables()"
```

## Reverse Proxy (Nginx Example)

In a production environment, it's crucial to place a reverse proxy like Nginx in front of your FastAPI application. Nginx can handle SSL termination, static file serving, load balancing, and protect your application from direct exposure.

**Example Nginx configuration (`/etc/nginx/sites-available/bookslot.conf`):**

```nginx
server {
    listen 80;
    server_name bookslot.app www.bookslot.app; # Replace with your domain

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name bookslot.app www.bookslot.app; # Replace with your domain

    ssl_certificate /etc/letsencrypt/live/bookslot.app/fullchain.pem; # Path to your SSL certificate
    ssl_certificate_key /etc/letsencrypt/live/bookslot.app/privkey.pem; # Path to your SSL key

    location /static/ {
        alias /app/static/; # Assuming your static files are in a 'static' directory at the app root
    }

    location / {
        proxy_pass http://localhost:8000; # Or the internal IP/hostname:port of your Docker container
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

*   **SSL Certificates:** Obtain SSL certificates using Certbot (Let's Encrypt) or your preferred method.
*   **Static Files:** Ensure your static files (CSS, JS, images) are properly collected and served by Nginx or a CDN. In the Docker image, they would typically be copied into the `/app/static` directory.

## Monitoring and Logging

*   **Logging:** Configure your application to log to `stdout` and `stderr` so Docker can capture them. Use a centralized logging solution (e.g., ELK stack, Grafana Loki, cloud-specific logging services) to collect and analyze logs.
*   **Monitoring:** Implement health checks and integrate with monitoring tools (e.g., Prometheus, Grafana, Datadog) to track application performance, errors, and resource usage.

## Continuous Integration/Continuous Deployment (CI/CD)

For robust deployments, consider setting up a CI/CD pipeline (e.g., GitHub Actions, GitLab CI, Jenkins) to automate testing, building Docker images, and deploying to your staging and production environments.

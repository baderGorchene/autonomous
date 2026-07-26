# BookSlot: Dead-Simple Booking Page for Local Service Businesses

BookSlot is a minimalistic, user-friendly booking page solution designed for solo service providers (salons, clinics, tutors, mechanics, coaches) who currently struggle with appointment management via chaotic WhatsApp messages. It offers a shareable booking link, self-service booking for customers, and instant notifications for owners.

## Business Idea & Problem Solved

Local service businesses often manage appointments through manual messaging, leading to confusion, missed bookings, and wasted time. BookSlot provides a streamlined, affordable alternative, allowing business owners to focus on their services rather than administrative overhead.

**Key Features (MVP):**
1.  **Owner Signup & Service Setup**: Business owners can easily create an account and define their services, pricing, and availability.
2.  **Public Booking Page**: A beautiful, mobile-first, and bilingual (English + Arabic/French) booking page accessible via a unique shareable link (e.g., `bookslot.app/their-name`).
3.  **Time Slot Availability**: Customers can view real-time availability and book open slots.
4.  **Email & WhatsApp Notifications**: Automated email confirmations for both customers and owners, and WhatsApp notifications for owners with booking details.
5.  **Simple Dashboard**: Owners get a clear overview of their upcoming bookings and can manage their profile.
6.  **No Customer Accounts**: Hassle-free booking for customers; no login required.
7.  **Bilingual Support**: English, Arabic, and French from day one, targeting underserved MENA and North Africa markets.

**Monetization**:
*   Free for up to 20 bookings/month.
*   $19/month for unlimited bookings.

**Target Audience**:
Solo service providers with 10-50 clients/week drowning in WhatsApp messages.

## Tech Stack

*   **Backend**: Python, FastAPI
*   **Database**: SQLite (for MVP, easily switchable to PostgreSQL)
*   **ORM**: SQLAlchemy
*   **Templating**: Jinja2
*   **Styling**: Modern CSS (responsive, mobile-first)
*   **Internationalization**: `gettext`
*   **Notifications**: SendGrid (Email), Twilio (WhatsApp)
*   **Deployment**: Docker, Gunicorn

## Local Development Setup

### Prerequisites

*   Python 3.9+
*   `pip`
*   `git`

### Steps

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/bookslot.git
    cd bookslot
    ```

2.  **Create a virtual environment and install dependencies**:
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Set up environment variables**:
    Create a `.env` file in the project root based on `.env.example`.
    ```ini
    # .env
    SECRET_KEY="a-very-secret-key-for-your-app"
    SENDGRID_API_KEY="your_sendgrid_api_key"
    TWILIO_ACCOUNT_SID="your_twilio_account_sid"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number
    GEMINI_API_KEY="" # Optional, if you integrate with Gemini
    DATABASE_URL="sqlite:///./bookslot.db" # Or a PostgreSQL URL for production
    ```
    *Replace placeholder values with your actual API keys.*

4.  **Initialize the database**:
    ```bash
    python -c "from src.database import Base, engine; Base.metadata.create_all(bind=engine)"
    ```
    This will create the `bookslot.db` SQLite file.

5.  **Run the application**:
    ```bash
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    ```
    The application will be accessible at `http://localhost:8000`.

## Running Tests

To run the automated test suite:

```bash
pytest
```

## Deployment Guide

This section outlines how to deploy BookSlot using Docker.

### Prerequisites for Deployment

*   Docker installed on your server.
*   Docker Compose (optional, but recommended for local testing and simpler deployments).
*   A domain name pointed to your server's IP address.
*   (Recommended) A reverse proxy like Nginx or Caddy to handle SSL termination and proxy requests to the Docker container.

### 1. Build the Docker Image

Navigate to the project root directory where `Dockerfile` is located and build the image:

```bash
docker build -t bookslot-app .
```
This command builds a Docker image named `bookslot-app` from your current directory.

### 2. Prepare Environment Variables

Create a production `.env` file on your server (e.g., in `/opt/bookslot/.env`) with your actual production API keys and database URL. For production, it's highly recommended to use a robust database like PostgreSQL or MySQL instead of SQLite.

Example `.env` for production (PostgreSQL):
```ini
# .env
SECRET_KEY="a-very-strong-and-unique-secret-key-for-production"
SENDGRID_API_KEY="your_production_sendgrid_api_key"
TWILIO_ACCOUNT_SID="your_production_twilio_account_sid"
TWILIO_AUTH_TOKEN="your_production_twilio_auth_token"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890"
GEMINI_API_KEY=""
DATABASE_URL="postgresql://user:password@db-host:5432/bookslot_db"
```

### 3. Run the Docker Container

#### Option A: Using `docker run` (Single container)

```bash
docker run -d \
  --name bookslot \
  --env-file /path/to/your/production/.env \
  -p 8000:8000 \
  bookslot-app
```
*   `-d`: Runs the container in detached mode (in the background).
*   `--name bookslot`: Assigns a name to your container.
*   `--env-file`: Specifies the path to your production `.env` file.
*   `-p 8000:8000`: Maps port 8000 of the host to port 8000 inside the container. If you have a reverse proxy, you might map to a different internal port or omit `-p` and use a Docker network.

#### Option B: Using `docker-compose` (Recommended for multi-service deployments or simpler management)

For a simple production setup using `docker-compose` without a separate database container (assuming an external database or a simple setup with SQLite if acceptable for your scale):

Create a `docker-compose.prod.yml` file:
```yaml
version: '3.8'

services:
  bookslot_app:
    image: bookslot-app # Use the image built previously
    container_name: bookslot_prod
    ports:
      - "8000:8000" # Map to an internal port if using a reverse proxy
    env_file:
      - /path/to/your/production/.env # Specify the path to your production .env file
    restart: always # Ensure the container restarts if it crashes
```

Then, run:
```bash
docker compose -f docker-compose.prod.yml up -d
```
*   `-f`: Specifies the compose file to use.
*   `up -d`: Creates and starts containers in detached mode.

### 4. Setting up a Reverse Proxy (Nginx/Caddy - Highly Recommended for Production)

For production, you should use a reverse proxy to handle SSL termination, serve static files, and forward requests to your BookSlot Docker container.

#### Example Nginx Configuration (`/etc/nginx/sites-available/bookslot.conf`):

```nginx
server {
    listen 80;
    server_name bookslot.app www.bookslot.app;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name bookslot.app www.bookslot.app;

    ssl_certificate /etc/letsencrypt/live/bookslot.app/fullchain.pem; # Path to your SSL cert
    ssl_certificate_key /etc/letsencrypt/live/bookslot.app/privkey.pem; # Path to your SSL key

    location / {
        proxy_pass http://localhost:8000; # Or the IP:PORT of your Docker container
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Optional: Serve static files directly from Nginx for better performance
    # You would need to mount your static files from the container or host to Nginx
    # location /static/ {
    #     alias /path/to/your/static/files/;
    #     expires 30d;
    #     add_header Cache-Control "public, no-transform";
    # }
}
```

After configuring Nginx, link it and reload:
```bash
sudo ln -s /etc/nginx/sites-available/bookslot.conf /etc/nginx/sites-enabled/
sudo nginx -t # Test configuration
sudo systemctl reload nginx
```

### 5. Database Management (Production)

For production, consider using a managed PostgreSQL/MySQL database service (e.g., AWS RDS, Azure Database, Google Cloud SQL) or deploying a separate PostgreSQL container using Docker Compose. Update `DATABASE_URL` in your `.env` accordingly.

## Internationalization (i18n)

The application supports English, Arabic, and French. Language can be toggled via the UI or by appending `?lang=ar` or `?lang=fr` to the URL.

## Contributing

(Future section)

## License

(Future section)

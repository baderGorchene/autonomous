# BookSlot - Dead Simple Booking Page

## Project Tagline
A dead-simple $19/month booking page for local service businesses (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp chaos.

## The Problem
Local service businesses, especially solo providers, often manage appointments manually through WhatsApp messages, leading to disorganization, missed bookings, and a lot of wasted time.

## The Solution
BookSlot provides a streamlined, shareable booking page (`bookslot.app/their-name`) where customers can self-book appointments. The owner receives instant WhatsApp/email notifications with booking details. No customer accounts needed, making the process frictionless.

## Target Audience
Solo service providers with 10-50 clients per week who are overwhelmed by manual appointment management.

## Key Features (MVP)
*   **Owner Signup & Service Setup:** Easy onboarding for business owners to define their services and availability.
*   **Public Booking Page:** A mobile-first, beautiful, and intuitive page for customers to book appointments.
*   **Time Slot Availability:** Owners can set their working hours and available slots.
*   **Email Confirmations:** Automated email notifications to both the owner and the customer upon booking.
*   **Simple Dashboard:** Owners get a clear overview of their upcoming bookings.
*   **Bilingual Support:** Fully localized in English, Arabic, and French from day one to cater to underserved MENA and North Africa markets.

## Monetization
*   **Free Tier:** Up to 20 bookings per month.
*   **Premium Tier:** $19/month for unlimited bookings.

## Tech Stack
*   **Backend:** FastAPI (Python)
*   **Database:** SQLAlchemy (ORM), SQLite (development), PostgreSQL (production recommended)
*   **Templating:** Jinja2
*   **Authentication:** JWT
*   **Notifications:** SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization (i18n):** Babel
*   **Deployment:** Docker, Gunicorn
*   **Testing:** Pytest, HTTPX

## Local Development Setup

### Prerequisites
*   Python 3.10+
*   pip
*   Git

### Steps
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/bookslot.git
    cd bookslot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file:**
    Copy `.env.example` to `.env` and fill in your credentials. This file should NOT be committed to version control.

5.  **Initialize the database:**
    The application will create a `sql_app.db` SQLite file by default. If using PostgreSQL, ensure it's running and update `DATABASE_URL` in `.env`.
    ```bash
    # This will create tables if they don't exist. 
    # In a real project with migrations (e.g., Alembic), you'd run 'alembic upgrade head'
    # For this project, tables are created on app startup if not present (in main.py's lifespan event or similar).
    # For manual creation, you can run a script that calls create_tables() from src/database.py
    python -c "from src.database import create_tables; create_tables()"
    ```

6.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be accessible at `http://localhost:8000`.

## Environment Variables (`.env.example`)
Create a `.env` file in the project root with the following variables:

```dotenv
# A strong, randomly generated string for JWT. Min length 32.
SECRET_KEY="your_super_secret_key_here_at_least_32_chars"

# Database URL. Example for SQLite:
DATABASE_URL="sqlite:///./sql_app.db"
# Example for PostgreSQL (replace with your credentials):
# DATABASE_URL="postgresql://user:password@db:5432/bookslot_db"

# SendGrid API Key for email notifications
SENDGRID_API_KEY="your_sendgrid_api_key"

# Twilio Account SID for WhatsApp notifications
TWILIO_ACCOUNT_SID="your_twilio_account_sid"
TWILIO_AUTH_TOKEN="your_twilio_auth_token"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number

# Base URL for the application, used for generating links in emails/notifications
# For local development: http://localhost:8000
# For production: https://bookslot.app
SERVER_NAME="http://localhost:8000"

# Set to True for testing environment (e.g., to use a test database)
TESTING=False
```

## Docker Setup

### Build and Run with Docker Compose (for development with PostgreSQL)
```bash
docker-compose up --build
```
This will start the FastAPI application and a PostgreSQL database. The app will be available at `http://localhost:8000`.

### Build and Run Docker Image (for production)
```bash
docker build -t bookslot-app .
docker run -p 8000:8000 --env-file ./.env bookslot-app
```

## Testing
To run the automated tests:
```bash
pytest
```

## Internationalization (i18n)

The application supports English, Arabic, and French.

### Adding new translations or updating existing ones:
1.  **Extract translatable strings:**
    ```bash
    pybabel extract -F babel.cfg -o locales/messages.pot src templates
    ```
2.  **Initialize a new locale (e.g., for Spanish 'es'):**
    ```bash
    pybabel init -i locales/messages.pot -d locales -l es
    ```
3.  **Update an existing locale (e.g., 'ar'):**
    ```bash
    pybabel update -i locales/messages.pot -d locales -l ar
    ```
4.  **Translate strings:** Edit the `.po` files in `locales/<locale_code>/LC_MESSAGES/messages.po`.
5.  **Compile translations:**
    ```bash
    pybabel compile -d locales
    ```

## Deployment
For production deployment, it is recommended to:
*   Use a robust database like PostgreSQL.
*   Set `SECRET_KEY` to a very strong, randomly generated value.
*   Configure `SENDGRID_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER` with actual production keys.
*   Set `SERVER_NAME` to your production domain (e.g., `https://bookslot.app`).
*   Use a process manager (like Gunicorn/Uvicorn with a reverse proxy like Nginx/Caddy) and containerization (Docker).
*   Implement proper logging and monitoring.

## Roadmap

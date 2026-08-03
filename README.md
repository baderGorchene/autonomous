# BookSlot - Dead-Simple Booking Page

BookSlot is a minimalist booking page solution designed for local service businesses. It aims to replace chaotic WhatsApp appointment management with a straightforward, shareable booking link. Customers can self-book, and business owners receive instant notifications. The platform supports bilingual (English + Arabic/French) operation from day one to cater to the MENA and North Africa markets.

## Features (MVP)

1.  **Owner Signup & Service Setup:** Business owners can register and define their services and availability.
2.  **Public Booking Page:** A mobile-first, beautiful page (`bookslot.app/their-name`) where customers can book.
3.  **Time Slot Availability:** Customers see real-time available time slots.
4.  **Email & WhatsApp Notifications:** Both owner and customer receive booking confirmations.
5.  **Simple Dashboard:** Owners can view their upcoming bookings.
6.  **Bilingual Support:** English, Arabic, and French translations.

## Monetization

*   **Free:** Up to 20 bookings/month.
*   **Premium ($19/month):** Unlimited bookings.

## Target Audience

Solo service providers (salons, clinics, tutors, mechanics, coaches) with 10-50 clients/week who are overwhelmed by manual appointment scheduling via messaging apps.

## Technologies Used

*   **Backend:** FastAPI (Python)
*   **Database:** SQLAlchemy ORM with SQLite (development/testing), PostgreSQL (production)
*   **Frontend:** Jinja2 Templates, Tailwind CSS (for styling)
*   **Authentication:** JWT (JSON Web Tokens)
*   **Notifications:** SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization (i18n):** `gettext`

## Setup and Local Development

### Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the project root based on `.env.example`:

```dotenv
# .env
SECRET_KEY="your-super-secret-key-for-jwt"
SENDGRID_API_KEY="your_sendgrid_api_key"
TWILIO_ACCOUNT_SID="your_twilio_account_sid"
TWILIO_AUTH_TOKEN="your_twilio_auth_token"
TWILIO_WHATSAPP_NUMBER="+1XXXXXXXXXX" # Your Twilio WhatsApp enabled number
DATABASE_URL="sqlite:///./sql_app.db" # Use a PostgreSQL URL in production
```

**Note:** For local development, `sqlite:///./sql_app.db` is sufficient. For production, switch to PostgreSQL.

### 4. Initialize Database and Run Migrations (Optional, for production-like setup)

BookSlot uses SQLAlchemy's declarative base. For initial setup, `main.py` creates tables automatically. For schema evolution, `Alembic` would be used.

*   **Initial Table Creation (Development):** The `main.py` will create tables if they don't exist on startup.

### 5. Run the application

```bash
uvicorn src.main:app --reload
```

The application will be accessible at `http://127.0.0.1:8000`.

## Running Tests

```bash
pytest
```

## Internationalization (i18n)

BookSlot uses `gettext` for internationalization. Translation files (`.po` and `.mo`) are located in the `locales/` directory.

### To update translations:

1.  **Extract new strings (from code and templates):**
    ```bash
    pybabel extract -F babel.cfg -o locales/messages.pot src/ templates/
    ```
    (You might need a `babel.cfg` file for this, see below)

2.  **Update `.po` files for each language:**
    ```bash
    pybabel update -i locales/messages.pot -d locales -l ar
    pybabel update -i locales/messages.pot -d locales -l fr
    ```

3.  **Translate strings** in `locales/ar/LC_MESSAGES/messages.po` and `locales/fr/LC_MESSAGES/messages.po`.

4.  **Compile `.mo` files (required for application to use translations):**
    ```bash
    pybabel compile -d locales
    ```

**`babel.cfg` example:**

```ini
[python: **.py]
[jinja2: **/templates/**.html]
encoding = utf-8
```

## Deployment

BookSlot can be deployed using Docker for easy containerization.

### 1. Build the Docker Image

```bash
docker build -t bookslot-app .
```

### 2. Run the Docker Container

```bash
docker run -d -p 80:8000 --name bookslot-instance \
    -e SECRET_KEY="your-production-secret-key" \
    -e SENDGRID_API_KEY="your_sendgrid_api_key" \
    -e TWILIO_ACCOUNT_SID="your_twilio_account_sid" \
    -e TWILIO_AUTH_TOKEN="your_twilio_auth_token" \
    -e TWILIO_WHATSAPP_NUMBER="+1XXXXXXXXXX" \
    -e DATABASE_URL="postgresql://user:password@host:port/dbname" \
    bookslot-app
```

**Important:** Ensure you replace placeholder values with actual production credentials and a PostgreSQL database URL.

### Example Deployment Script (`deploy.sh`)

This is a basic example. For production, consider using orchestration tools like Docker Compose, Kubernetes, or cloud-specific deployment services.

```bash
#!/bin/bash

# Stop and remove existing container (if any)
docker stop bookslot-instance || true
docker rm bookslot-instance || true

# Build the Docker image
docker build -t bookslot-app .

# Run the new container
docker run -d -p 80:8000 --name bookslot-instance \
    -e SECRET_KEY="${BOOKSLOT_SECRET_KEY}" \
    -e SENDGRID_API_KEY="${BOOKSLOT_SENDGRID_API_KEY}" \
    -e TWILIO_ACCOUNT_SID="${BOOKSLOT_TWILIO_ACCOUNT_SID}" \
    -e TWILIO_AUTH_TOKEN="${BOOKSLOT_TWILIO_AUTH_TOKEN}" \
    -e TWILIO_WHATSAPP_NUMBER="${BOOKSLOT_TWILIO_WHATSAPP_NUMBER}" \
    -e DATABASE_URL="${BOOKSLOT_DATABASE_URL}" \
    bookslot-app

echo "BookSlot deployed and running on port 80"
```

To use `deploy.sh`, set the environment variables in your shell or CI/CD system before running the script:

```bash
export BOOKSLOT_SECRET_KEY="your-production-secret-key"
export BOOKSLOT_SENDGRID_API_KEY="your_sendgrid_api_key"
export BOOKSLOT_TWILIO_ACCOUNT_SID="your_twilio_account_sid"
export BOOKSLOT_TWILIO_AUTH_TOKEN="your_twilio_auth_token"
export BOOKSLOT_TWILIO_WHATSAPP_NUMBER="+1XXXXXXXXXX"
export BOOKSLOT_DATABASE_URL="postgresql://user:password@host:port/dbname"

bash deploy.sh
```

## Project Structure

```
bookslot/
├── src/
│   ├── __init__.py
│   ├── config.py             # Application settings and environment variables
│   ├── crud.py               # Database Create, Read, Update, Delete operations
│   ├── database.py           # SQLAlchemy engine and session setup
│   ├── dependencies.py       # FastAPI dependencies (e.g., auth, DB session)
│   ├── i18n_config.py        # Internationalization setup for Jinja2
│   ├── main.py               # Main FastAPI application, routes, middleware
│   ├── models.py             # SQLAlchemy ORM models
│   ├── notifications.py      # Email and WhatsApp notification logic
│   └── schemas.py            # Pydantic models for data validation
├── templates/
│   ├── base.html             # Base template for common HTML structure
│   ├── booking_page.html     # Public booking interface
│   ├── booking_confirmation.html # Booking success page
│   ├── dashboard.html        # Owner dashboard
│   ├── index.html            # Landing page
│   ├── login.html            # Owner login form
│   ├── profile.html          # Owner profile edit form
│   └── signup.html           # Owner signup form
├── locales/
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po
│   │       └── messages.mo
│   ├── fr/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po
│   │       └── messages.mo
│   └── messages.pot          # Translation template
├── tests/
│   └── test_main.py          # Pytest integration tests
├── .env.example              # Example environment variables
├── Dockerfile                # Docker build instructions
├── deploy.sh                 # Example deployment script
├── requirements.txt          # Python dependencies
└── README.md                 # Project documentation
```

# BookSlot

BookSlot is a dead-simple booking page solution for local service businesses. It allows business owners to create a shareable booking link, enabling customers to self-book appointments. Owners receive WhatsApp/email notifications for new bookings, and customers get email confirmations. The platform is designed to be bilingual (English + Arabic/French) from day one.

## Features (MVP)

1.  **Owner Signup & Service Setup:** Business owners can register and define their services and availability.
2.  **Public Booking Page:** A mobile-first, beautiful public page (`bookslot.app/their-name`) where customers can view services and book slots without needing an account.
3.  **Time Slot Availability:** Owners can set their availability, and the booking page will reflect open slots.
4.  **Email Confirmations:** Automated email notifications to both the owner and the customer upon booking.
5.  **WhatsApp Notifications:** Optional WhatsApp notifications to the owner and customer for booking confirmations.
6.  **Simple Dashboard:** Owners get a dashboard to view upcoming bookings.
7.  **Bilingual Support:** English, Arabic, and French languages are supported from the start.
8.  **Comprehensive Error Handling:** Robust error handling for booking submissions and profile updates.

## Monetization

*   **Free Tier:** Up to 20 bookings/month.
*   **Premium Tier:** $19/month for unlimited bookings.

## Target Audience

Solo service providers (salons, clinics, tutors, mechanics, coaches) who manage 10-50 clients/week and are currently overwhelmed by WhatsApp-based appointment management.

## Project Structure

```
.env.example
Dockerfile
README.md
requirements.txt
static/
├── css/
│   └── style.css
locales/
├── ar/
│   └── LC_MESSAGES/
│       └── messages.po
├── fr/
│   └── LC_MESSAGES/
│       └── messages.po
templates/
├── base.html
├── booking_confirmation.html
├── booking_page.html
├── dashboard.html
├── login.html
├── register.html
src/
├── __init__.py
├── config.py
├── crud.py
├── database.py
├── i18n_config.py
├── main.py
├── models.py
├── notifications.py
├── schemas.py
└── security.py
tests/
└── test_app.py
```

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd BookSlot
    ```
2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows: venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set up environment variables:**
    Copy `.env.example` to `.env` and fill in your details.
    ```bash
    cp .env.example .env
    ```
    *   `SECRET_KEY`: A strong, random string for JWT. `openssl rand -hex 32` can generate one.
    *   `DATABASE_URL`: Your database connection string (e.g., `sqlite:///./bookslot.db` for SQLite).
    *   `SENDGRID_API_KEY`: Your SendGrid API key for email notifications.
    *   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`: Your Twilio credentials for WhatsApp notifications.

5.  **Run database migrations (if using Alembic, otherwise models will be created on startup for SQLite):**
    *(Alembic setup is beyond MVP, for SQLite `models.Base.metadata.create_all` handles it)*

6.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

## Running Tests

To run the automated tests, ensure `pytest` and `httpx` are installed (they are in `requirements.txt`):

```bash
pytest
```

## Deployment (Docker)

1.  **Build the Docker image:**
    ```bash
    docker build -t bookslot-app .
    ```
2.  **Run the Docker container:**
    ```bash
    docker run -p 8000:8000 --env-file ./.env bookslot-app
    ```
    Ensure your `.env` file is properly configured for the production environment.

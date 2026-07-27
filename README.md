# BookSlot

BookSlot is a dead-simple booking page solution for local service businesses. It allows business owners to create a shareable booking link, enabling their customers to self-book appointments. Owners receive WhatsApp/email notifications for new bookings, and customers don't need accounts. The platform supports bilingual (English + Arabic/French) functionality from day one, targeting underserved markets.

## Features (MVP)

*   **Owner Signup & Service Setup:** Business owners can register and configure their services and availability.
*   **Public Booking Page:** A mobile-first, beautiful public page (`bookslot.app/their-name`) where customers can view services and book appointments.
*   **Time Slot Availability:** Owners define their availability, and customers can only book within those slots.
*   **Email Confirmations:** Both the owner and the customer receive email confirmations with booking details.
*   **WhatsApp Notifications:** Optional WhatsApp notifications for owners and customers.
*   **Simple Dashboard:** Owners get a dashboard to view upcoming bookings and manage their profile.
*   **Bilingual Support:** English, Arabic, and French languages are supported.

## Monetization

*   Free for up to 20 bookings/month.
*   $19/month for unlimited bookings.

## Technology Stack

*   **Backend:** FastAPI (Python)
*   **Database:** SQLAlchemy (ORM) with SQLite (for MVP, easily swappable)
*   **Frontend:** Jinja2 (templating), Tailwind CSS (for styling), Vanilla JavaScript
*   **Authentication:** JWT (JSON Web Tokens)
*   **Notifications:** SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization:** gettext, Babel
*   **Deployment:** Docker, Gunicorn, Uvicorn

## Setup and Installation

### Prerequisites

*   Python 3.8+
*   pip
*   Git
*   Docker (optional, for containerized deployment)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: `venv\Scripts\activate`
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Create a `.env` file in the project root based on `.env.example`:

```bash
cp .env.example .env
```

Edit the `.env` file with your actual credentials:

```ini
SECRET_KEY="your_super_secret_key_here"
SENDGRID_API_KEY="your_sendgrid_api_key_here"
TWILIO_ACCOUNT_SID="your_twilio_account_sid_here"
TWILIO_AUTH_TOKEN="your_twilio_auth_token_here"
TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886" # Your Twilio WhatsApp Sandbox number
GEMINI_API_KEY="" # Optional: If you plan to integrate Gemini API
DATABASE_URL="sqlite:///./bookslot.db" # Or your PostgreSQL/MySQL URL
```

### 5. Run Database Migrations (if using Alembic, not explicitly set up in MVP)

For SQLite, tables are created on app startup in `main.py`. For production, consider using Alembic for migrations.

### 6. Compile Translations

Ensure `babel` is installed (`pip install babel`).
```bash
python -m babel compile -d locales
```

### 7. Run the application

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at `http://127.0.0.1:8000`.

### 8. Accessing the Application

*   **Owner Signup:** `http://127.0.0.1:8000/signup`
*   **Owner Login:** `http://127.0.0.1:8000/login`
*   **Dashboard:** `http://127.0.0.1:8000/dashboard`
*   **Public Booking Page:** `http://127.0.0.1:8000/bookslot/{your-business-slug}` (e.g., `http://127.0.0.1:8000/bookslot/my-salon`)

## Running Tests

```bash
pytest
```

## Docker Deployment

To build and run the application using Docker:

```bash
docker build -t bookslot .
docker run -p 8000:8000 --env-file ./.env bookslot
```

This will build a Docker image and run a container, making the application accessible on `http://localhost:8000`.

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── crud.py
│   ├── database.py
│   ├── i18n_config.py
│   ├── main.py
│   ├── models.py
│   ├── notifications.py
│   ├── schemas.py
│   └── security.py
├── templates/
│   ├── booking_page.html
│   ├── booking_confirmation.html
│   ├── dashboard.html
│   ├── login.html
│   ├── owner_signup.html
│   └── profile.html
├── locales/
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       └── messages.po
│   └── fr/
│       └── LC_MESSAGES/
│           └── messages.po
├── tests/
│   ├── __init__.py
│   ├── test_i18n.py
│   └── test_main.py
├── .env.example
├── Dockerfile
├── README.md
└── requirements.txt
```
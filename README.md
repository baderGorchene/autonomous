# BookSlot

BookSlot is a dead-simple booking page for local service businesses. It allows business owners to create a shareable booking link, customers to book appointments without needing an account, and both parties to receive WhatsApp/email notifications.

## Features (MVP)

*   **Owner Signup & Service Setup:** Business owners can create an account, define their services, and set their availability.
*   **Public Booking Page:** A mobile-first, beautiful booking page accessible via a unique slug (e.g., `bookslot.app/their-name`).
*   **Time Slot Availability:** Customers can see and select available time slots.
*   **Email & WhatsApp Notifications:** Automated email and WhatsApp confirmations for both the owner and the customer upon booking.
*   **Simple Dashboard:** Owners get a dashboard to view upcoming bookings and manage their profile, services, and availability.
*   **Bilingual Support:** Full English, Arabic, and French support from day one, targeting MENA and North Africa markets.
*   **Comprehensive Error Handling:** Robust error handling for all user interactions and API calls.
*   **Responsive UI/UX:** Polished user interface and user experience for both desktop and mobile.
*   **Deployment Configuration:** Includes Dockerfile and deployment scripts.

## Technologies Used

*   **Backend:** FastAPI (Python)
*   **Database:** SQLAlchemy ORM with SQLite (development) / PostgreSQL (production)
*   **Frontend:** Jinja2 Templates, HTML, CSS, JavaScript (minimal)
*   **Authentication:** JWT (JSON Web Tokens)
*   **Notifications:** SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization (i18n):** `gettext`
*   **Deployment:** Docker

## Setup and Installation

### Prerequisites

*   Python 3.11+
*   `pip` (Python package installer)
*   `git`
*   Docker (for containerized deployment)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: `venv\Scripts\activate`
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the project root based on `.env.example`.

```ini
SECRET_KEY="your_super_secret_key_here"
DATABASE_URL="sqlite:///./sql_app.db" # For local development
# DATABASE_URL="postgresql://user:password@host:port/dbname" # For production

SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY"
TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID"
TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN"
TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886" # Your Twilio WhatsApp Sandbox number or official number
GEMINI_API_KEY="" # Optional, if you integrate Gemini later
```

*   **`SECRET_KEY`**: A strong, random string for JWT signing.
*   **`DATABASE_URL`**: SQLAlchemy database URL. Use `sqlite:///./sql_app.db` for local development. For production, consider PostgreSQL (e.g., `postgresql://user:password@host:port/dbname`).
*   **`SENDGRID_API_KEY`**: Your API key from SendGrid for sending emails.
*   **`TWILIO_ACCOUNT_SID`**, **`TWILIO_AUTH_TOKEN`**, **`TWILIO_WHATSAPP_NUMBER`**: Credentials for Twilio to send WhatsApp messages. `TWILIO_WHATSAPP_NUMBER` should be in the format `whatsapp:+<countrycode><number>`.

### 4. Initialize Database and Compile Translations

The database tables will be created automatically when the application starts if they don't exist.
Translations need to be compiled from `.po` to `.mo` files.

```bash
# Compile .po files to .mo files
find locales -name "*.po" -execdir msgfmt -o {}.mo {} \;
```

### 5. Run the application locally

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be accessible at `http://127.0.0.1:8000`.

### 6. Accessing the Application

*   **Home Page:** `http://127.0.0.1:8000/`
*   **Register:** `http://127.0.0.1:8000/register`
*   **Login:** `http://127.0.0.1:8000/login`
*   **Dashboard:** `http://127.0.0.1:8000/dashboard` (requires login)
*   **Public Booking Page:** `http://127.0.0.1:8000/{your-slug}` (e.g., `http://127.0.0.1:8000/mybusiness`)

## Testing

To run the automated tests:

```bash
pytest
```

## Deployment with Docker

### 1. Build the Docker image

```bash
docker build -t bookslot-app .
```

### 2. Run the Docker container

```bash
docker run -p 8000:8000 --env-file ./.env bookslot-app
```

The application will be available on port 8000 of your host machine.

## Project Structure

```
.
├── Dockerfile
├── README.md
├── .env.example
├── requirements.txt
├── locales/
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po
│   │       └── messages.mo
│   └── fr/
│       └── LC_MESSAGES/
│           ├── messages.po
│           └── messages.mo
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
├── static/
│   ├── style.css
│   └── dashboard.js
├── templates/
│   ├── booking_confirmation.html
│   ├── booking_page.html
│   ├── dashboard.html
│   ├── index.html
│   ├── login.html
│   └── register.html
└── tests/
    └── test_main.py
```
# BookSlot

BookSlot is a dead-simple booking page solution designed for local service businesses. It helps owners manage appointments efficiently, moving away from the chaos of WhatsApp messages to a streamlined online booking system.

## Business Idea

BookSlot aims to be an affordable ($19/month) booking page for solo service providers (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp. Key features include:
*   A shareable public booking link (e.g., `bookslot.app/their-name`).
*   Customers can book themselves without needing an account.
*   Owners receive WhatsApp/email notifications with booking details.
*   Bilingual support (English + Arabic/French) to target the MENA and North Africa markets.

## MVP Features

1.  **Owner Signup & Service Setup**: Owners can register and define their services and availability.
2.  **Public Booking Page**: A mobile-first, beautiful page for customers to book.
3.  **Time Slot Availability**: Customers can see and select available time slots.
4.  **Email Confirmation**: Both owner and customer receive booking confirmations.
5.  **Simple Dashboard**: Owners can view upcoming bookings and manage their profile.
6.  **Bilingual Support**: English, Arabic, and French translations.

## Monetization

*   Free for up to 20 bookings/month.
*   $19/month for unlimited bookings.

## Tech Stack

*   **Backend**: FastAPI (Python)
*   **Database**: SQLite (for MVP, easily upgradeable to PostgreSQL)
*   **Frontend**: Jinja2 Templates, HTML, CSS, JavaScript (minimal)
*   **Notifications**: SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization**: `gettext` / `Babel`
*   **Deployment**: Docker, Gunicorn, Uvicorn

## Setup (Local Development)

### Prerequisites

*   Python 3.9+
*   pip
*   Git

### 1. Clone the repository

```bash
git clone <repository-url>
cd bookslot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the project root based on `.env.example`.

```
# .env
SECRET_KEY="your-super-secret-key-for-jwt"
SENDGRID_API_KEY="your_sendgrid_api_key"
TWILIO_ACCOUNT_SID="your_twilio_account_sid"
TWILIO_AUTH_TOKEN="your_twilio_auth_token"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp Sandbox number or actual number
GEMINI_API_KEY="your_gemini_api_key" # Optional, if using Gemini for any future features
DATABASE_URL="sqlite:///./bookslot.db" # Or your PostgreSQL URL, e.g., postgresql://user:password@host:port/dbname
```
*Replace placeholder values with your actual credentials.*

### 4. Database Initialization

The SQLite database `bookslot.db` will be created automatically on first run. For other databases, ensure connection details in `DATABASE_URL` are correct.

### 5. Run the Application

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be accessible at `http://127.0.0.1:8000`.

## Deployment with Docker

### 1. Build the Docker image

```bash
docker build -t bookslot .
```

### 2. Run the Docker container

```bash
docker run -d --name bookslot-app -p 80:8000 --env-file .env bookslot
```
Ensure your `.env` file is correctly configured with all necessary environment variables for production.

The application will be accessible at `http://localhost`.

## Internationalization (i18n)

BookSlot supports English, Arabic, and French.
*   **Translation Files**: Located in `locales/{lang}/LC_MESSAGES/messages.po`.
*   **Updating Translations**:
    1.  Extract new strings: `pybabel extract -F babel.cfg -o locales/messages.pot .`
    2.  Update existing language files: `pybabel update -i locales/messages.pot -d locales`
    3.  Compile translations: `pybabel compile -d locales`

## Running Tests

```bash
pytest
```

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── main.py             # Main FastAPI application
│   ├── models.py           # SQLAlchemy models
│   ├── schemas.py          # Pydantic schemas
│   ├── crud.py             # CRUD operations
│   ├── security.py         # Authentication and password hashing
│   ├── database.py         # Database connection
│   ├── config.py           # Application settings
│   ├── notifications.py    # Email/WhatsApp notifications
│   └── i18n_config.py      # Internationalization setup
├── templates/              # Jinja2 HTML templates
│   ├── base.html
│   ├── booking_page.html
│   ├── booking_confirmation.html
│   ├── dashboard.html
│   ├── login.html
│   ├── signup.html
│   └── ...
├── static/                 # CSS, JS, images
│   ├── css/
│   ├── js/
│   └── img/
├── locales/                # Internationalization files
│   ├── ar/LC_MESSAGES/messages.po
│   ├── fr/LC_MESSAGES/messages.po
│   └── messages.pot
├── tests/                  # Automated tests
│   ├── test_i18n.py
│   ├── test_booking.py
│   ├── test_auth.py
│   └── ...
├── .env.example            # Example environment variables
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker deployment configuration
├── README.md               # Project documentation
└── babel.cfg               # Babel configuration for i18n
```

## License

[MIT License](LICENSE) (or choose your preferred license)
# BookSlot

BookSlot is a dead-simple $19/month booking page for local service businesses (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp chaos. The owner gets a shareable link (bookslot.app/their-name), customers book themselves, and the owner gets a WhatsApp/email notification with the booking details. No accounts needed for customers. Bilingual (English + Arabic/French) from day one to target the underserved MENA and North Africa market.

## Features (MVP)

1.  **Owner Signup & Service Setup**: Business owners can create an account, define their services, and set their availability.
2.  **Public Booking Page**: A clean, mobile-first booking page accessible via a unique slug (e.g., `bookslot.app/their-name`).
3.  **Time Slot Availability**: Customers can see available time slots based on the owner's defined schedule.
4.  **Email Confirmation**: Automated email notifications to both the customer and the owner upon successful booking.
5.  **Simple Dashboard**: Owners can view upcoming bookings and manage their profile.
6.  **Bilingual Support**: English, Arabic, and French from day one.

## Getting Started

### Prerequisites

*   Python 3.11+
*   pip
*   (Optional for local development) virtualenv

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/bookslot.git
    cd bookslot
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: `venv\Scripts\activate`
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables**:
    Create a `.env` file in the project root based on `.env.example`.

    ```ini
    # .env
    SECRET_KEY="your-super-secret-key-for-jwt"
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    SENDGRID_API_KEY="your_sendgrid_api_key"
    TWILIO_ACCOUNT_SID="your_twilio_account_sid"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="+1xxxxxxxxxx" # Your Twilio WhatsApp enabled number, e.g., +15017122661

    DATABASE_URL="sqlite:///./sql_app.db"
    # For PostgreSQL: DATABASE_URL="postgresql://user:password@host:port/dbname"
    ```
    *   `SECRET_KEY`: A strong, random string for JWT token signing.
    *   `SENDGRID_API_KEY`: Your API key for SendGrid to send emails.
    *   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`: Your Twilio credentials for WhatsApp notifications.
    *   `DATABASE_URL`: Connection string for your database. For local development, `sqlite:///./sql_app.db` is sufficient.

5.  **Compile translations**:
    ```bash
    python -m babel compile -d locales
    ```

### Running the Application

```bash
uvicorn src.main:app --reload
```
The application will be available at `http://127.0.0.1:8000`.

### Running Tests

```bash
pytest
```

## Deployment

A basic `Dockerfile` is provided for containerized deployment.

```bash
docker build -t bookslot .
docker run -p 8000:8000 bookslot
```
Ensure your `.env` variables are correctly configured for the production environment (e.g., using environment variables directly in Docker or Kubernetes, rather than a `.env` file).

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── config.py             # Application settings and environment variables
│   ├── crud.py               # Database Create, Read, Update, Delete operations
│   ├── database.py           # SQLAlchemy engine and session setup
│   ├── i18n_config.py        # Jinja2 and Gettext internationalization setup
│   ├── main.py               # FastAPI application entry point, routes, and dependencies
│   ├── models.py             # SQLAlchemy ORM models
│   ├── notifications.py      # Email and WhatsApp notification logic
│   ├── schemas.py            # Pydantic schemas for data validation
│   └── security.py           # Password hashing and JWT token management
├── templates/
│   ├── base.html             # Base template for all pages
│   ├── booking_confirmation.html # Booking success page
│   ├── booking_page.html     # Public booking page for customers
│   ├── dashboard.html        # Owner dashboard
│   ├── home.html             # Landing page
│   ├── login.html            # Owner login page
│   └── signup.html           # Owner signup page
├── locales/
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po   # Arabic translation file
│   │       └── messages.mo   # Compiled Arabic translation
│   └── fr/
│       └── LC_MESSAGES/
│           ├── messages.po   # French translation file
│           └── messages.mo   # Compiled French translation
├── static/
│   ├── css/
│   │   └── style.css         # Main stylesheet
│   └── js/
│       └── main.js           # Main JavaScript file
├── tests/
│   └── test_main.py          # Automated tests for core functionality
├── .env.example              # Example environment variables
├── Dockerfile                # Docker configuration for deployment
├── README.md                 # Project documentation
└── requirements.txt          # Python dependencies
```

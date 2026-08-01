# BookSlot - Dead-Simple Booking Page

BookSlot is a minimalist booking page solution for local service businesses. It aims to replace the "WhatsApp chaos" of appointment management with a simple, shareable booking link.

## Features

*   **Owner Signup & Service Setup:** Business owners can easily create an account, define their services, and set their availability.
*   **Public Booking Page:** A mobile-first, beautiful booking page (`bookslot.app/their-name`) where customers can self-book without needing an account.
*   **Time Slot Availability:** Customers see available time slots based on the owner's defined schedule.
*   **Email & WhatsApp Notifications:** Both the owner and customer receive notifications upon booking confirmation.
*   **Simple Dashboard:** Owners can view their upcoming bookings and manage their profile, services, and availability.
*   **Bilingual Support:** English, Arabic, and French are supported from day one to cater to diverse markets.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

*   Python 3.8+
*   pip (Python package installer)
*   Git

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/bookslot.git
    cd bookslot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure environment variables:**
    Create a `.env` file in the project root (same directory as `main.py`) and populate it with your settings.
    ```
    SECRET_KEY="your_super_secret_key_here"
    DATABASE_URL="sqlite:///./bookslot.db"
    # Optional: For email notifications (e.g., SendGrid)
    SENDGRID_API_KEY=""
    # Optional: For WhatsApp notifications (e.g., Twilio)
    TWILIO_ACCOUNT_SID=""
    TWILIO_AUTH_TOKEN=""
    TWILIO_WHATSAPP_NUMBER="" # e.g., +1234567890
    # Optional: For AI integration (if planned)
    GEMINI_API_KEY=""
    ```
    *   `SECRET_KEY`: A strong, random string for JWT token signing.
    *   `DATABASE_URL`: SQLAlchemy database connection string. `sqlite:///./bookslot.db` for a local SQLite file.
    *   Notification keys are optional for basic functionality but required for email/WhatsApp features.

### Running the Application

```bash
uvicorn src.main:app --reload
```
The application will be accessible at `http://127.0.0.1:8000`.

### Running Tests

To run the automated tests, ensure your virtual environment is active and `pytest` is installed (it's in `requirements.txt`).

```bash
pytest
```
This will execute all tests in the `tests/` directory.

### Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── config.py             # Application settings
│   ├── crud.py               # Database Create, Read, Update, Delete operations
│   ├── database.py           # SQLAlchemy setup and session management
│   ├── i18n_config.py        # Jinja2 i18n setup
│   ├── main.py               # FastAPI application, routes, and logic
│   ├── models.py             # SQLAlchemy ORM models
│   ├── notifications.py      # Email (SendGrid) and WhatsApp (Twilio) notification logic
│   ├── schemas.py            # Pydantic models for data validation and serialization
│   └── security.py           # Password hashing and JWT token handling
├── templates/
│   ├── booking_page.html     # Public booking interface
│   ├── booking_confirmation.html # Booking success page
│   ├── dashboard.html        # Owner's dashboard
│   ├── login.html            # Owner login page
│   └── signup.html           # Owner signup page
├── locales/                  # Internationalization files
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       └── messages.po   # Arabic translations
│   └── fr/
│       └── LC_MESSAGES/
│           └── messages.po   # French translations
├── tests/
│   └── test_integration.py   # Comprehensive integration tests
├── .env                      # Environment variables (local config)
├── requirements.txt          # Python dependencies
└── README.md                 # Project documentation
```

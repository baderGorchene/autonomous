# BookSlot

BookSlot is a dead-simple booking page for local service businesses designed to streamline appointment management and reduce WhatsApp chaos. It offers a shareable booking link, customer self-service booking, and instant WhatsApp/email notifications for business owners.

## Features

*   **Owner Signup & Service Setup**: Business owners can register, set up their services, and define their availability.
*   **Public Booking Page**: A mobile-first, user-friendly page where customers can easily book appointments without needing an account.
*   **Time Slot Availability**: Intelligent management of available booking slots.
*   **Email Confirmations**: Automated email notifications to both the customer and the business owner upon booking.
*   **Simple Dashboard**: An owner dashboard to view upcoming bookings and manage profile settings.
*   **Bilingual Support**: Fully localized in English, Arabic, and French to cater to the MENA and North Africa markets.
*   **Error Handling**: Robust error handling for booking submissions and profile updates.

## Monetization

*   Free for up to 20 bookings/month.
*   $19/month for unlimited bookings.

## Getting Started

### Prerequisites

*   Python 3.9+
*   `pip` (Python package installer)
*   `git` (for cloning the repository)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/bookslot.git
    cd bookslot
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the project root with the following variables:
    ```
    SECRET_KEY="your-super-secret-key"
    SENDGRID_API_KEY="your-sendgrid-api-key"
    TWILIO_ACCOUNT_SID="your-twilio-account-sid"
    TWILIO_AUTH_TOKEN="your-twilio-auth-token"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number
    GEMINI_API_KEY="your-gemini-api-key" # If integrated for AI features
    ```

### Running the Application

1.  **Run database migrations (if any, or just create tables for SQLite):**
    The current setup uses SQLAlchemy declarative base, so tables are created on startup if `models.Base.metadata.create_all(bind=engine)` is called. This is usually handled in `main.py`.

2.  **Start the server:**
    ```bash
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    ```
    (Assuming `main.py` is in the `src` directory)

    For production, use Gunicorn:
    ```bash
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.main:app -b 0.0.0.0:8000
    ```

### Running Tests

```bash
pymain.py:app -b 0.0.0.0:8000test
```

## Project Structure

```
.
├── locales/
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       └── messages.po
│   └── fr/
│       └── LC_MESSAGES/
│           └── messages.po
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── crud.py
│   ├── database.py
│   ├── i18n_config.py
│   ├── main.py        # Main FastAPI application
│   ├── models.py      # SQLAlchemy models
│   ├── notifications.py # Email/WhatsApp notifications
│   ├── schemas.py     # Pydantic schemas
│   └── security.py    # Authentication/Authorization logic
├── static/            # CSS, JS, images
│   ├── css/
│   └── js/
├── templates/
│   ├── base.html
│   ├── booking_confirmation.html
│   ├── booking_page.html
│   ├── dashboard.html
│   └── login.html
├── tests/
│   ├── __init__.py
│   ├── test_i18n.py
│   ├── test_integration.py
│   └── test_unit.py
├── .env.example       # Example environment variables file
├── Dockerfile         # Docker configuration
└── requirements.txt   # Python dependencies
```

## Deployment

Refer to the `Dockerfile` for containerized deployment instructions.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

[Specify your license here, e.g., MIT License]

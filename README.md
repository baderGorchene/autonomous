# BookSlot: A Simple Booking Page for Local Service Businesses

BookSlot offers a dead-simple, shareable booking page for local service businesses to manage appointments efficiently, moving beyond WhatsApp chaos.

## Features

*   **Owner Signup & Service Setup**: Business owners can register and define their services and availability.
*   **Public Booking Page**: Customers can easily book appointments via a shareable link (e.g., `bookslot.app/their-name`).
*   **Time Slot Availability**: Intelligent management of available booking slots.
*   **Notifications**: Owners receive WhatsApp/email notifications for new bookings; customers receive email confirmations.
*   **Simple Dashboard**: Owners can view upcoming bookings and manage their profile.
*   **Bilingual Support**: English + Arabic/French from day one, targeting MENA and North Africa markets.
*   **Mobile-First Design**: Responsive and user-friendly interface.

## Monetization

*   Free for up to 20 bookings/month.
*   $19/month for unlimited bookings.

## Target Audience

Solo service providers who have 10-50 clients/week and are looking for a straightforward solution to streamline their booking process.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

*   Python 3.9+
*   `pip` (Python package installer)
*   `git` (for cloning the repository)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/bookslot.git # Replace with actual repo URL
    cd bookslot
    ```

2.  **Create and activate a virtual environment:**
    It's highly recommended to use a virtual environment to manage dependencies.
    ```bash
    python -m venv venv
    # On macOS/Linux:
    source venv/bin/activate
    # On Windows:
    .\venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Database Setup:**
    The application uses SQLite by default. If you wish to use a different database, update `DATABASE_URL` in your `.env` file.
    ```bash
    python -c "from src.database import create_tables; create_tables()"
    ```
    This command will create the necessary database tables.

### Configuration

Create a `.env` file in the project root directory (same level as `src` folder) based on `src/config.py`.
```
SECRET_KEY="YOUR_SUPER_SECRET_KEY_HERE_MIN_32_CHARS"
DATABASE_URL="sqlite:///./sql_app.db"
SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY" # Optional, for email notifications
TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID" # Optional, for WhatsApp notifications
TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # e.g., 'whatsapp:+14155238886'
SERVER_NAME="http://localhost:8000" # Base URL for your application
```
*   **`SECRET_KEY`**: A strong, random string essential for JWT security. Generate a long random string (e.g., using `openssl rand -hex 32`).
*   **`DATABASE_URL`**: Connection string for your database.
*   **`SENDGRID_API_KEY`**: Required for email notifications.
*   **`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`**: Required for WhatsApp notifications.
*   **`SERVER_NAME`**: The base URL where your application is hosted.

### Running the Application

To run the FastAPI application:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```
The application will be accessible at `http://localhost:8000`.

### Running Tests

Ensure you have installed the test dependencies (`pytest`, `pytest-asyncio`, `httpx`).
```bash
pytest
```

### Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── config.py             # Application settings and configurations
│   ├── crud.py               # Database Create, Read, Update, Delete operations
│   ├── database.py           # Database connection and session management
│   ├── dependencies.py       # Dependency injection for FastAPI
│   ├── i18n.py               # Internationalization (i18n) utilities
│   ├── main.py               # Main FastAPI application entry point
│   ├── models.py             # SQLAlchemy models
│   ├── notifications.py      # Email and WhatsApp notification services
│   ├── schemas.py            # Pydantic schemas for data validation
│   ├── security.py           # Authentication and password hashing
│   └── templates/            # Jinja2 HTML templates
│       ├── base.html
│       ├── booking_confirmation.html
│       ├── booking_page.html
│       ├── dashboard.html
│       ├── login.html
│       └── signup.html
├── locales/                  # Translation files (e.g., ar, fr)
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       └── messages.po
│   └── fr/
│       └── LC_MESSAGES/
│           └── messages.po
├── tests/                    # Unit and integration tests
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_i18n.py
│   └── test_security.py
├── .env.example              # Example environment variables file
├── requirements.txt          # Python dependencies
└── README.md                 # Project documentation
```

### Deployment

For production deployment, consider using a WSGI server like Gunicorn with Uvicorn workers behind a reverse proxy (Nginx/Caddy). Ensure all environment variables are properly set in your production environment.

Example Gunicorn command:
```bash
gunicorn src.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

### License

[MIT](https://choosealicense.com/licenses/mit/)

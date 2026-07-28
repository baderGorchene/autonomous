# BookSlot

BookSlot is a dead-simple $19/month booking page for local service businesses. It allows owners to create a shareable booking link, customers to book themselves without accounts, and provides notifications to the owner. It supports bilingual (English + Arabic/French) operation from day one.

## Features

- Owner signup and service setup
- Public booking page
- Time slot availability management
- Email confirmations to both parties
- Simple dashboard for upcoming bookings
- Bilingual support (English, Arabic, French)

## Setup and Installation

### Prerequisites

- Python 3.9+
- pip
- Docker (optional, for containerized deployment)

### Local Development

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd bookslot
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the project root based on `.env.example`.

    ```ini
    # .env
    SECRET_KEY="your-super-secret-key-for-jwt"
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    SENDGRID_API_KEY="your-sendgrid-api-key"
    TWILIO_ACCOUNT_SID="your-twilio-account-sid"
    TWILIO_AUTH_TOKEN="your-twilio-auth-token"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # e.g., whatsapp:+14155238886
    GEMINI_API_KEY="" # Optional, if not used

    DATABASE_URL="sqlite:///./sql_app.db" # For local development, or a PostgreSQL connection string
    ```

5.  **Run database migrations (if applicable):**
    If using Alembic or similar, run migration commands here. For SQLite, `uvicorn` will create the `sql_app.db` file automatically on first run if models are defined and `Base.metadata.create_all(engine)` is called.

6.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

### Running Tests

```bash
pytest
```

### Docker Deployment

1.  **Build the Docker image:**
    ```bash
    docker build -t bookslot .
    ```

2.  **Run the Docker container:**
    Ensure you have your `.env` variables available to the container. You can pass them directly or mount the `.env` file.

    ```bash
    docker run -d -p 8000:8000 --env-file ./.env bookslot
    ```
    The application will be available at `http://localhost:8000`.

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── crud.py
│   ├── database.py
│   ├── i18n_config.py
│   ├── main.py             # Main FastAPI application
│   ├── models.py           # SQLAlchemy models
│   ├── notifications.py    # Email/WhatsApp notifications
│   ├── schemas.py          # Pydantic schemas
│   └── security.py         # Authentication utilities
├── templates/              # Jinja2 templates (booking_page.html, dashboard.html etc.)
├── static/                 # Static files (CSS, JS, images)
├── locales/                # Translation files (ar/LC_MESSAGES/messages.po, fr/LC_MESSAGES/messages.po)
├── tests/                  # Automated tests
├── .env.example            # Example environment variables
├── Dockerfile              # Docker configuration
├── README.md               # Project documentation
└── requirements.txt        # Python dependencies
```

## Contributing

... (Guidelines for contribution)

## License

... (License information)
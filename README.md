# BookSlot: Dead-Simple Booking Page for Local Service Businesses

## Project Tagline
Streamline appointments, ditch WhatsApp chaos.

## Business Idea
BookSlot offers a dead-simple, $19/month booking page for local service businesses (salons, clinics, tutors, mechanics, coaches) drowning in WhatsApp appointment management. Owners get a shareable link (e.g., `bookslot.app/their-name`), customers book themselves, and the owner receives WhatsApp/email notifications. No customer accounts needed. Bilingual (English + Arabic/French) from day one, targeting underserved MENA and North Africa markets.

## Minimum Viable Product (MVP) Features
1.  **Owner Signup & Service Setup**: Business owners can register and define their services and availability.
2.  **Public Booking Page**: A mobile-first, beautiful, and shareable booking link for customers.
3.  **Time Slot Availability**: Customers can see and select available time slots.
4.  **Email Confirmations**: Automated booking confirmations sent to both the customer and the owner.
5.  **Simple Dashboard**: Owners can view upcoming bookings and manage their profile.
6.  **Bilingual Support**: English, Arabic, and French translations available from launch.

## Monetization
*   **Free Tier**: Up to 20 bookings per month.
*   **Premium Tier**: $19/month for unlimited bookings.
*   **Target Audience**: Solo service providers handling 10-50 clients/week.

## Tech Stack
*   **Backend**: FastAPI (Python)
*   **Database**: SQLAlchemy ORM with SQLite (for MVP)
*   **Frontend**: Jinja2 Templates, HTML, CSS (TailwindCSS/Custom CSS for mobile-first design)
*   **Authentication**: JWT
*   **Notifications**: SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization (i18n)**: gettext
*   **Deployment**: Docker, Gunicorn

## Installation (Local Development)

### Prerequisites
*   Python 3.8+
*   `pip` (Python package installer)
*   `git`
*   `gettext` (for `msgfmt` command, usually available on Linux/macOS or via WSL on Windows)

### Steps
1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/bookslot.git
    cd bookslot
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables**:
    Create a `.env` file in the root directory of the project based on `.env.example`.
    ```
    # .env
    SECRET_KEY="your_super_secret_key_here_CHANGE_THIS_IN_PRODUCTION"
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    # For email notifications
    SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY"

    # For WhatsApp notifications (optional, if Twilio is configured)
    TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID"
    TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886" # Your Twilio WhatsApp Sandbox number or actual number

    # Database configuration
    DATABASE_URL="sqlite:///./sql_app.db" # Use sqlite for local development
    TESTING=False

    # Optional: For future AI features
    GEMINI_API_KEY=""
    ```
    **Important**: For production deployments, ensure `SECRET_KEY` is a strong, randomly generated string.

5.  **Initialize the Database**:
    ```bash
    python -c "from src.database import create_tables; create_tables()"
    ```
    This will create the `sql_app.db` SQLite file and necessary tables.

6.  **Compile Message Catalogs for i18n**:
    ```bash
    # For each language you have (e.g., ar, fr, en)
    # This command compiles .po files into .mo files required by gettext
    # Example for Arabic:
    msgfmt -o locales/ar/LC_MESSAGES/messages.mo locales/ar/LC_MESSAGES/messages.po
    # Example for French:
    msgfmt -o locales/fr/LC_MESSAGES/messages.mo locales/fr/LC_MESSAGES/messages.po
    # ... and so on for any other languages, including English if you have a .po for it.
    ```

## Running the Application

### Local Development Server
```bash
uvicorn src.main:app --reload
```
The application will be accessible at `http://127.0.0.1:8000`.

### Running with Docker (Recommended for Production)

1.  **Build the Docker Image**:
    ```bash
    docker build -t bookslot .
    ```

2.  **Run with Docker Compose**:
    Ensure your `.env` file is configured correctly.
    ```bash
    docker-compose up --build -d
    ```
    The application will be accessible at `http://localhost:8000`.

    To stop the services:
    ```bash
    docker-compose down
    ```

## Testing
To run the automated tests:
```bash
pytest
```
Ensure you have `pytest` and `httpx` installed (`pip install pytest httpx`).

## Internationalization (i18n)
BookSlot supports multiple languages (English, Arabic, French).
*   Translation files are located in the `locales` directory.
*   To add a new language:
    1.  Create a new language directory (e.g., `locales/es/LC_MESSAGES`).
    2.  Create `messages.po` in that directory.
    3.  Extract new strings from your code/templates using `pybabel extract -F babel.cfg -o locales/messages.pot .` (requires `babel` package).
    4.  Initialize new language: `pybabel init -i locales/messages.pot -d locales -l es`
    5.  Translate strings in `locales/es/LC_MESSAGES/messages.po`.
    6.  Compile translations: `msgfmt -o locales/es/LC_MESSAGES/messages.mo locales/es/LC_MESSAGES/messages.po`.
*   The language can be toggled via a query parameter (e.g., `?lang=ar` or `?lang=fr`).

## Security Considerations
*   **Secret Key**: `SECRET_KEY` in `.env` must be a strong, unique, and securely stored value in production. Do not commit it to version control.
*   **Password Hashing**: Passwords are hashed using `bcrypt`.
*   **Input Validation**: Pydantic schemas are used for robust input validation.
*   **JWT Security**: Access tokens are signed and have an expiration time.
*   **Environment Variables**: Sensitive information is stored in environment variables, not directly in code.

## Future Enhancements
*   Payment Gateway Integration
*   Calendar Sync (Google Calendar, Outlook)
*   Recurring Appointments
*   Customer Management (CRM light)
*   Promotional Tools
*   Admin Panel for advanced settings
*   More robust analytics and reporting

## Contributing
Please refer to the project's issue tracker for current development goals and how to contribute.

## License
[Specify your license here, e.g., MIT License]

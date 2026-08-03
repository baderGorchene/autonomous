# BookSlot

BookSlot is a dead-simple booking page solution designed for local service businesses (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp chaos. It provides a shareable link (e.g., `bookslot.app/their-name`) where customers can book themselves. The business owner receives WhatsApp/email notifications with booking details, and customers don't need to create accounts.

The application is built with FastAPI, SQLAlchemy, and Jinja2, with a focus on mobile-first design and bilingual support (English, Arabic, French) to target underserved markets.

## Features

*   **Owner Signup & Service Setup**: Business owners can register, set up their business profile, define services, and specify their availability.
*   **Public Booking Page**: A clean, mobile-first, and bilingual page (`bookslot.app/their-name`) where customers can easily book services.
*   **Time Slot Availability**: Customers can see and select available time slots based on the owner's defined availability.
*   **Email & WhatsApp Notifications**: Automated booking confirmations sent to both the customer and the owner.
*   **Simple Dashboard**: Owners get a dashboard to view upcoming bookings and manage their profile.
*   **Bilingual Support**: Full internationalization (i18n) for English, Arabic, and French.
*   **No Customer Accounts**: Streamlined booking process for customers.
*   **Monetization (MVP Strategy)**: Free for up to 20 bookings/month, $19/month for unlimited.

## Technology Stack

*   **Backend**: FastAPI (Python)
*   **Database**: SQLAlchemy (ORM), SQLite (development/MVP), PostgreSQL (production recommended)
*   **Templating**: Jinja2
*   **Frontend**: HTML, CSS (Pico.css for minimal styling), JavaScript
*   **Authentication**: JWT (JSON Web Tokens)
*   **Notifications**: SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization**: `python-gettext`
*   **Containerization**: Docker

## Setup and Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Create a `.env` file in the project root based on `.env.example`:

```ini
# .env
SECRET_KEY="your-super-secret-key-that-you-must-change"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

SENDGRID_API_KEY="your-sendgrid-api-key"
TWILIO_ACCOUNT_SID="your-twilio-account-sid"
TWILIO_AUTH_TOKEN="your-twilio-auth-token"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number (e.g., whatsapp:+14155238886)

DATABASE_URL="sqlite:///./sql_app.db" # For production, consider PostgreSQL: postgresql://user:password@host:port/dbname
# TESTING=True # Uncomment for testing environment
```
**Important**: For production, ensure `SECRET_KEY` is a strong, randomly generated string and kept secret. Configure `DATABASE_URL` for a production-grade database like PostgreSQL.

### 5. Initialize Database

The application will automatically create tables on startup if they don't exist. For a fresh start, you can manually run:
```bash
python -c "from src.database import create_tables; create_tables()"
```
*(Note: For development, SQLite is used. For production, a proper migration tool like Alembic would be recommended.)*

### 6. Running the Application

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be accessible at `http://localhost:8000`.

### 7. Accessing the Application

*   **Signup**: `http://localhost:8000/signup`
*   **Login**: `http://localhost:8000/login`
*   **Dashboard**: `http://localhost:8000/dashboard` (requires login)
*   **Public Booking Page**: `http://localhost:8000/your-business-slug` (e.g., after signup, if your slug is `my-salon`, it would be `http://localhost:8000/my-salon`)

## Internationalization (i18n)

The application supports English, Arabic, and French. Language selection is handled via a cookie, which can be set by clicking the language toggles on any page.

To update translations:
1.  Extract new strings:
    ```bash
    pybabel extract -F babel.cfg -o locales/messages.pot src/ templates/
    ```
    *(You might need a `babel.cfg` file in your project root with content like: `[python: src/**.py]\n[jinja2: templates/**.html]\nencoding = utf-8`)*
2.  Update existing `.po` files:
    ```bash
    pybabel update -i locales/messages.pot -d locales
    ```
3.  Compile translations:
    ```bash
    pybabel compile -d locales
    ```

## Testing

To run the tests:

```bash
pytest
```

The tests use an in-memory SQLite database to ensure isolation and speed.

## Deployment with Docker

### 1. Build the Docker image

```bash
docker build -t bookslot-app .
```

### 2. Run the Docker container

```bash
docker run -d --name bookslot -p 80:8000 --env-file ./.env bookslot-app
```
*   `-d`: Run in detached mode.
*   `--name bookslot`: Assign a name to your container.
*   `-p 80:8000`: Map host port 80 to container port 8000 (where FastAPI runs). Adjust host port as needed.
*   `--env-file ./.env`: Pass environment variables from your `.env` file into the container. Ensure this file contains production-ready secrets.

For production deployments, consider using a reverse proxy like Nginx or Caddy in front of your Docker container for SSL termination, load balancing, and static file serving.

## Future Enhancements

*   **Advanced Scheduling**: More complex availability rules (e.g., breaks, holidays, multiple staff).
*   **Payment Integration**: Stripe, PayPal for booking payments.
*   **Admin Panel**: More robust features for owners (e.g., booking management, client list, reporting).
*   **Recurring Bookings**.
*   **Calendar Integration**: Google Calendar, Outlook Calendar sync.
*   **Customization**: Allow owners to customize booking page colors, logo.
*   **Subscription Management**: Implement the free/paid tier logic.
*   **PostgreSQL**: Use Alembic for database migrations in production.

# BookSlot - Dead-Simple Booking Page for Local Service Businesses

BookSlot is a web application designed to provide a dead-simple booking page for local service businesses (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp chaos. It aims to simplify appointment management by offering a shareable booking link, self-service booking for customers, and automated notifications for business owners.

## Features (MVP):

1.  **Owner Signup & Service Setup Page**: Business owners can register and configure their services.
2.  **Public Booking Page**: A mobile-first, beautiful, and shareable booking page (`bookslot.app/their-name`) where customers can book services without needing an account.
3.  **Time Slot Availability**: Owners can define their availability, supporting one-off and recurring schedules. The system calculates and displays available slots.
4.  **Email & WhatsApp Notifications**: Owners receive WhatsApp/email notifications with booking details. Customers receive email confirmations.
5.  **Simple Dashboard**: Owners get a dashboard to view upcoming bookings, manage services and availability, and update their profile.
6.  **Bilingual Support**: Fully bilingual from day one (English + Arabic/French) to target underserved MENA and North Africa markets.
7.  **Customer Accounts**: Customers can register, login, and manage their profiles.
8.  **Review/Rating System**: Customers can submit reviews and ratings for services, displayed on the public booking page and owner dashboard.
9.  **Subscription Management**: Integrated Stripe payment gateway for premium subscriptions, allowing owners to upgrade and manage their plans.
10. **Analytics**: Basic analytics on the owner dashboard (monthly booking counts, popular services).
11. **Admin Panel**: Initial admin panel for managing owners and subscriptions with basic CRUD operations.
12. **Recurring Bookings**: Support for customers to book recurring appointments.
13. **SEO Optimization**: Basic SEO measures for public booking pages.
14. **Performance Optimization**: Basic caching and performance improvements.
15. **Security Hardening & Testing**: Thorough security audit, hardening measures, and automated security tests.
16. **Comprehensive Logging**: Detailed logging for application and security events.

## Monetization:

*   **Free Tier**: Up to 20 bookings/month.
*   **Premium Tier**: $19/month for unlimited bookings.

## Target Audience:

Solo service providers who have 10-50 clients/week and are overwhelmed by manual appointment management via WhatsApp.

## Technologies Used:

*   **Backend**: FastAPI (Python)
*   **Database**: PostgreSQL (via SQLAlchemy ORM)
*   **Frontend**: Jinja2 Templates, HTML, CSS (TailwindCSS/custom for mobile-first design), JavaScript
*   **Authentication**: JWT (JSON Web Tokens)
*   **Notifications**: SendGrid (Email), Twilio (WhatsApp)
*   **Payments**: Stripe (for subscriptions)
*   **Internationalization**: `gettext` for translations, `babel` for locale-aware formatting.
*   **Testing**: Pytest
*   **Deployment**: Docker

## Project Setup (Development)

### Prerequisites

*   Python 3.8+
*   Poetry (recommended for dependency management) or pip
*   Docker (for PostgreSQL, optional but recommended)

### 1. Clone the repository:

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Set up a virtual environment and install dependencies:

Using Poetry:

```bash
poetry install
poetry shell
```

Using pip:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Setup (using Docker Compose for PostgreSQL):

Create a `docker-compose.yml` file in the project root:

```yaml
version: '3.8'
services:
  db:
    image: postgres:13-alpine
    restart: always
    environment:
      POSTGRES_DB: bookslot_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

volumes:
  pg_data:
```

Start the database:

```bash
docker-compose up -d
```

### 4. Environment Variables:

Create a `.env` file in the project root (or copy `.env.example` and fill it out):

```ini
DATABASE_URL="postgresql://user:password@localhost/bookslot_db"
SECRET_KEY="YOUR_SUPER_SECRET_KEY_FOR_JWT"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

# SendGrid (Email Notifications)
SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY"
SENDGRID_SENDER_EMAIL="your_verified_sender_email@example.com"

# Twilio (WhatsApp Notifications)
TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID"
TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN"
TWILIO_WHATSAPP_NUMBER="+1XXXXXXXXXX" # Your Twilio WhatsApp enabled number

# Stripe (Payments)
STRIPE_SECRET_KEY="sk_test_YOUR_STRIPE_SECRET_KEY"
STRIPE_PUBLIC_KEY="pk_test_YOUR_STRIPE_PUBLIC_KEY"
STRIPE_WEBHOOK_SECRET="whsec_YOUR_STRIPE_WEBHOOK_SECRET"
STRIPE_PREMIUM_PRICE_ID="price_YOUR_STRIPE_PRICE_ID" # e.g., price_12345ABCDEF

# Base URL for public booking pages
BASE_URL="http://localhost:8000" # Or your deployed domain
```

### 5. Run Database Migrations (using Alembic - if implemented, otherwise create tables directly):

If Alembic is configured, run:

```bash
alembic upgrade head
```

Otherwise, ensure `src/database.py`'s `Base.metadata.create_all(engine)` is called (e.g., by importing `models` in `main.py` and running it once).

### 6. Run the application:

```bash
uvicorn src.main:app --reload
```

The application will be available at `http://localhost:8000`.

## Running Tests

```bash
pytest
```

## Internationalization (i18n)

Translation files are located in the `locales/` directory. To update translations:

1.  **Extract strings**: `pybabel extract -F babel.cfg -o locales/messages.pot .`
2.  **Initialize new language (e.g., 'ar' for Arabic)**: `pybabel init -i locales/messages.pot -d locales -l ar`
3.  **Update existing language**: `pybabel update -i locales/messages.pot -d locales -l ar`
4.  **Compile translations**: `pybabel compile -d locales`

## Logging

The application uses Python's standard `logging` module to capture application and security events.
Logs are stored in the `logs/` directory at the project root.
- `logs/app.log`: Contains general application information, errors, and warnings.
- `logs/security.log`: Contains security-related events such as successful/failed login attempts, registration, and unauthorized access.

Both log files implement log rotation, keeping up to 5 backup files of 10MB each.

## Deployment

### Docker

A `Dockerfile` is provided for containerization. Build and run with Docker:

```bash
docker build -t bookslot .
docker run -p 8000:8000 --env-file ./.env bookslot
```

For production, consider using Docker Compose for multiple services (app, db, nginx) and a process manager like Gunicorn.

### Gunicorn (for production)

```bash
gunicorn src.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Ensure you configure environment variables appropriately for your production environment.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

# BookSlot

**Dead-simple booking page for local service businesses.**

BookSlot offers a streamlined, $19/month booking page solution for local service providers like salons, clinics, tutors, mechanics, and coaches who struggle with appointment management via chaotic WhatsApp messages. We provide a unique, shareable link (e.g., `bookslot.app/their-name`), allowing customers to self-book appointments. Owners receive instant WhatsApp/email notifications with booking details. No customer accounts are needed, ensuring a friction-less experience. BookSlot is built with bilingual support (English + Arabic/French) from day one, targeting the underserved MENA and North Africa markets.

## Business Idea

The core problem BookSlot solves is the time-consuming and error-prone process of managing appointments manually, especially common among solo service providers using WhatsApp. Our solution empowers business owners to reclaim their time, reduce no-shows through automated confirmations, and expand their reach with a professional, easy-to-use booking system.

## Features

**MVP Includes:**

1.  **Owner Signup & Service Setup:** Business owners can register, define their services, set prices, and specify their availability.
2.  **Public Booking Page:** A mobile-first, beautiful, and shareable booking page (`bookslot.app/their-name`) where customers can easily view services and available time slots.
3.  **Time Slot Availability:** Intelligent display of available booking slots based on owner's configured availability and existing bookings.
4.  **Email & WhatsApp Notifications:** Automated booking confirmations sent to both the customer and the business owner.
5.  **Simple Dashboard:** Owners get a personalized dashboard to view upcoming bookings, manage their profile, and update services/availability.
6.  **Bilingual Support (i18n):** Full support for English, Arabic, and French, with a language toggle on public and dashboard pages.
7.  **Robust Error Handling:** Comprehensive error handling for booking submissions and profile updates, providing clear feedback to users.
8.  **Responsive UI/UX:** Polished user interface designed for an optimal experience across all devices.

## Tech Stack

*   **Backend:** FastAPI (Python)
*   **Database:** SQLAlchemy (ORM) with SQLite (for MVP/development), PostgreSQL (for production)
*   **Frontend:** Jinja2 Templates, HTML, CSS, JavaScript (minimal)
*   **Authentication:** JWT (JSON Web Tokens)
*   **Notifications:** SendGrid (Email), Twilio (WhatsApp)
*   **Internationalization:** Babel
*   **Dependency Management:** pip, `requirements.txt`
*   **Containerization:** Docker
*   **Testing:** Pytest

## Local Development Setup

### Prerequisites

Ensure you have the following installed:

*   Python 3.9+
*   pip (Python package installer)
*   Docker (Optional, for containerized deployment)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd bookslot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the project root directory (next to `src` folder) with the following content. **Replace placeholder values with your actual keys.**

    ```dotenv
    # .env example
    SECRET_KEY="your-super-secret-key-at-least-32-chars-long" # IMPORTANT: Generate a strong, unique key
    SENDGRID_API_KEY="SG.YOUR_SENDGRID_API_KEY"
    TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number
    DATABASE_URL="sqlite:///./sql_app.db" # Use sqlite for development
    SERVER_NAME="http://localhost:8000" # Base URL for link generation
    TESTING=False
    ```
    *   **`SECRET_KEY`**: Crucial for JWT security. Generate a strong, random string (e.g., using `openssl rand -hex 32`).
    *   **`SENDGRID_API_KEY`**: Obtain from your SendGrid account.
    *   **`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`**: Obtain from your Twilio account.

5.  **Initialize the database:**
    ```bash
    python -c "from src.database import create_tables; create_tables()"
    ```
    This will create `sql_app.db` and the necessary tables.

### Running the Application

To start the FastAPI application:

```bash
uvicorn src.main:app --reload
```

The application will be accessible at `http://localhost:8000`.

*   **Owner Signup:** `http://localhost:8000/register`
*   **Owner Login:** `http://localhost:8000/login`
*   **Owner Dashboard:** `http://localhost:8000/dashboard` (requires login)
*   **Public Booking Page:** `http://localhost:8000/book/{owner_slug}` (replace `{owner_slug}` with an owner's slug after registration)

## Testing

To run the automated tests:

```bash
pytest
```

Ensure `TESTING=True` is set in your `.env` file or environment variables when running tests to use a separate test database (if configured in `src/config.py` and `src/database.py` to handle `TESTING` flag). The current setup uses a default `sqlite:///./sql_app.db`, which would be shared unless `DATABASE_URL` is explicitly changed for testing. For robust testing, modify `DATABASE_URL` in `.env` for testing to `sqlite:///./test.db`.

## Deployment

BookSlot is designed for containerized deployment using Docker.

### Dockerfile

A `Dockerfile` is provided in the project root.

### Building the Docker Image

```bash
docker build -t bookslot-app .
```

### Running the Docker Container

```bash
docker run -d -p 8000:8000 --env-file ./.env bookslot-app
```
**Important:** For production, ensure you use a persistent database (e.g., PostgreSQL) and a robust secrets management system. Update `DATABASE_URL` in your `.env` (or environment variables) for production to point to your PostgreSQL instance.

Example production `.env` might look like:
```dotenv
SECRET_KEY="your-strong-production-secret-key"
SENDGRID_API_KEY="SG.YOUR_PRODUCTION_SENDGRID_API_KEY"
TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_AUTH_TOKEN="your_production_twilio_auth_token"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890"
DATABASE_URL="postgresql://user:password@db-host:5432/bookslot_db"
SERVER_NAME="https://bookslot.app" # Your production domain
TESTING=False
```

## Monetization

*   **Free Tier:** Up to 20 bookings per month.
*   **Paid Tier:** $19/month for unlimited bookings.

## Internationalization (i18n)

BookSlot supports English, Arabic, and French. Translation files are located in the `locales/` directory.

*   To extract new strings for translation:
    ```bash
    pybabel extract -F babel.cfg -o locales/messages.pot src/ templates/
    ```
*   To initialize a new language (e.g., Spanish 'es'):
    ```bash
    pybabel init -i locales/messages.pot -d locales -l es
    ```
*   To update existing language catalogs:
    ```bash
    pybabel update -i locales/messages.pot -d locales
    ```
*   To compile translations:
    ```bash
    pybabel compile -d locales
    ```
    (This must be run after any changes to `.po` files for them to take effect.)

## Contact

For support or inquiries, please contact [support@bookslot.app](mailto:support@bookslot.app).

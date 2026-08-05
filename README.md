# BookSlot - Simple Booking Page for Local Services

BookSlot offers a dead-simple, shareable online booking page for local service businesses (salons, clinics, tutors, mechanics, coaches) to manage appointments efficiently, moving away from WhatsApp chaos. Customers can book themselves, and the owner receives instant WhatsApp/email notifications with booking details. No customer accounts are needed, making the booking process frictionless. The platform is bilingual (English + Arabic/French) from day one, targeting underserved markets like MENA and North Africa.

## Features

*   **Owner Signup & Service Setup:** Easy registration and configuration of services and availability.
*   **Public Booking Page:** A mobile-first, beautifully designed public page for customers to book services.
*   **Time Slot Availability:** Owners define their available time slots, which customers can select.
*   **Automated Notifications:** Email and WhatsApp notifications for both owners and customers upon booking.
*   **Simple Dashboard:** Owners get a dashboard to view upcoming bookings and manage their profile.
*   **Bilingual Support:** Full English, Arabic, and French support with a language toggle.
*   **Error Handling:** Robust error handling for booking submissions and profile updates.
*   **Responsive UI/UX:** Optimized user experience across various devices.

## Tech Stack

*   **Backend:** FastAPI, Pydantic
*   **Database:** SQLAlchemy (ORM), SQLite (development), PostgreSQL (production)
*   **Templating:** Jinja2
*   **Internationalization:** Babel
*   **Notifications:** SendGrid (Email), Twilio (WhatsApp)
*   **Authentication:** JWT

## Local Development Setup

Follow these steps to get BookSlot running on your local machine.

### Prerequisites

*   Python 3.9+
*   pip (Python package installer)
*   virtualenv (recommended)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/bookslot.git
    cd bookslot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file:**
    Create a file named `.env` in the project root directory with the following content. Replace placeholder values with your actual credentials.
    ```env
    SECRET_KEY="your_super_secret_key_here_at_least_32_chars"
    DATABASE_URL="sqlite:///./sql_app.db"
    SENDGRID_API_KEY="your_sendgrid_api_key"
    TWILIO_ACCOUNT_SID="your_twilio_account_sid"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number
    SERVER_NAME="http://localhost:8000"
    # GEMINI_API_KEY="your_gemini_api_key" # Currently not used
    ```
    *   `SECRET_KEY`: A strong, random string essential for JWT security. Generate one with `openssl rand -hex 32`.
    *   `DATABASE_URL`: For local development, SQLite is used. For production, a PostgreSQL URL is recommended.
    *   `SENDGRID_API_KEY`: Obtain this from your SendGrid account.
    *   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`: Obtain these from your Twilio account. Ensure your Twilio number is WhatsApp-enabled.
    *   `SERVER_NAME`: The base URL of your application. Important for generating correct links in emails.

5.  **Initialize the database:**
    ```bash
    python -m src.database create_tables
    ```
    This will create the `sql_app.db` file for SQLite.

6.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be accessible at `http://localhost:8000`.

## Running Tests

To run the automated tests, ensure you have installed `pytest` (included in `requirements.txt`).

```bash
pytest
```

## Deployment (Production)

For production deployment, consider the following:

1.  **Environment Variables:** All variables in the `.env` file for local setup **must** be set as environment variables in your production environment. `SECRET_KEY`, `DATABASE_URL`, `SERVER_NAME`, and all notification service keys are critical.

    *   **Database:** It is highly recommended to use a robust database like PostgreSQL for production. Update `DATABASE_URL` to point to your PostgreSQL instance (e.g., `postgresql://user:password@host:port/dbname`).
    *   **`SERVER_NAME`**: Set this to your actual domain (e.g., `https://bookslot.app`).

2.  **Running the Application:** Use a production-ready ASGI server like Gunicorn with Uvicorn workers.

    ```bash
    gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
    ```
    Adjust `-w` (number of workers) based on your server's CPU cores.

3.  **Reverse Proxy:** For better security, performance, and SSL termination, use a reverse proxy like Nginx or Caddy in front of Gunicorn.

4.  **Containerization:** A `Dockerfile` is provided in the root directory for building a Docker image of the application, facilitating containerized deployment to platforms like Docker Swarm, Kubernetes, or cloud services.

5.  **Database Migrations:** For managing database schema changes in production, consider integrating a tool like Alembic (not included in MVP but recommended for long-term projects).

## Internationalization (i18n)

BookSlot supports English, Arabic, and French. To add new languages or update existing translations:

1.  **Extract new messages:**
    ```bash
    pybabel extract -F babel.cfg -o locales/messages.pot src
    ```
    (A `babel.cfg` file should be present in the project root to configure extraction.)

2.  **Initialize a new language (e.g., Spanish 'es'):**
    ```bash
    pybabel init -i locales/messages.pot -d locales -l es
    ```

3.  **Update existing languages:**
    ```bash
    pybabel update -i locales/messages.pot -d locales
    ```

4.  **Translate:** Edit the `.po` files located in `locales/<lang_code>/LC_MESSAGES/messages.po`.

5.  **Compile translations:**
    ```bash
    pybabel compile -d locales
    ```

## Monetization

BookSlot offers a free tier for up to 20 bookings per month. For unlimited bookings, a subscription of $19/month is available.
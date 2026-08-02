# BookSlot - README

This project aims to provide a dead-simple $19/month booking page for local service businesses.

## Business Idea
BookSlot targets local service businesses (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp chaos. The owner gets a shareable link (bookslot.app/their-name), customers book themselves, and the owner gets a WhatsApp/email notification with the booking details. No accounts needed for customers. Bilingual (English + Arabic/French) from day one to target the underserved MENA and North Africa market. MVP has: (1) owner signup + service setup page, (2) public booking page, (3) time slot availability, (4) email confirmation to both parties, (5) a simple dashboard showing upcoming bookings. Monetization: free for up to 20 bookings/month, $19/month for unlimited. Target: solo service providers who have 10-50 clients/week and are drowning in WhatsApp messages.

## Project Structure

-   `src/main.py`: Main FastAPI application entry point.
-   `src/models.py`: SQLAlchemy ORM models for database interaction.
-   `src/schemas.py`: Pydantic models for request/response validation.
-   `src/security.py`: Handles password hashing, JWT token generation, and authentication.
-   `src/crud.py`: Database Create, Read, Update, Delete operations.
-   `src/database.py`: Database connection and session management.
-   `src/config.py`: Application settings and environment variable loading.
-   `src/notifications.py`: Handles sending email and WhatsApp notifications.
-   `src/i18n_config.py`: Internationalization (i18n) setup for Jinja2 templates.
-   `templates/`: HTML templates for rendering UI.
-   `locales/`: Translation files for internationalization (e.g., `ar/LC_MESSAGES/messages.po`, `fr/LC_MESSAGES/messages.po`).
-   `tests/`: Unit and integration tests.
-   `Dockerfile`: Docker build instructions for the application.
-   `requirements.txt`: Python dependencies.

## Setup and Local Development

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd bookslot
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Create a `.env` file:**
    Create a file named `.env` in the root directory and populate it with your environment variables. Example:
    ```
    SECRET_KEY="your_super_secret_key_here"
    SENDGRID_API_KEY="your_sendgrid_api_key"
    TWILIO_ACCOUNT_SID="your_twilio_account_sid"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="+1234567890" # Your Twilio WhatsApp enabled number
    GEMINI_API_KEY="your_gemini_api_key"
    DATABASE_URL="sqlite:///./sql_app.db" # For local development
    TESTING="False"
    ```

4.  **Run database migrations (if any) and create tables:**
    For SQLite, the tables will be created automatically on first run if they don't exist based on `Base.metadata.create_all(bind=engine)` in `database.py`. For production/staging with PostgreSQL, you might use Alembic for migrations.

5.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

## Testing

To run the tests, ensure you have `pytest` installed (included in `requirements.txt`):

```bash
pytest
```

Tests are configured to use an in-memory SQLite database to ensure isolation and speed.

## Deployment to Staging Environment

This section outlines the steps to deploy BookSlot to a staging environment using Docker and Docker Compose.

### Prerequisites
- Docker and Docker Compose installed on your system.

### Steps

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd bookslot
    ```

2.  **Create a `.env` file:**
    Create a file named `.env` in the root directory of the project. This file will hold sensitive environment variables required by the application.
    ```
    SECRET_KEY="your_strong_secret_key_here" # Generate with 'openssl rand -hex 32'
    SENDGRID_API_KEY="your_sendgrid_api_key"
    TWILIO_ACCOUNT_SID="your_twilio_account_sid"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="your_twilio_whatsapp_number"
    GEMINI_API_KEY="your_gemini_api_key"
    ```
    **Note:** For a real staging environment, these should be managed securely (e.g., Kubernetes secrets, AWS Secrets Manager, etc.) and not committed to version control.

3.  **Deploy with Docker Compose:**
    From the root directory of the project, run:
    ```bash
    docker-compose up -d --build
    ```
    This command will:
    -   Build the Docker image for the application (if not already built or if changes detected).
    -   Start the PostgreSQL database service.
    -   Start the BookSlot application service, linking it to the database.
    -   Run services in detached mode (`-d`).

4.  **Access the Staging Application:**
    The application will be accessible at `http://localhost:8000` (or the IP address/domain where Docker is running).

### User Acceptance Testing (UAT)

Once deployed, perform the following checks on the staging environment:

-   **Owner Onboarding:**
    -   Register a new owner account.
    -   Login with the new account.
    -   Set up services and availability.
    -   Update profile information.
-   **Public Booking Page:**
    -   Access the public booking page (`/book/{owner_slug}`).
    -   Verify correct display of services and available slots.
    -   Submit a booking as a customer.
    -   Verify booking confirmation page.
-   **Email/WhatsApp Notifications:**
    -   Check if the owner receives email/WhatsApp notifications for new bookings.
    -   Check if the customer receives email confirmations.
-   **Owner Dashboard:**
    -   Login to the owner dashboard.
    -   Verify the list of upcoming bookings is accurate.
    -   Test profile update functionality.
-   **Internationalization (i18n):**
    -   Verify language toggle (English/Arabic/French) on both public booking page and owner dashboard.
    -   Ensure translations are correctly applied.
-   **Error Handling:**
    -   Test various invalid inputs for signup, booking, and profile updates to ensure appropriate error messages are displayed.

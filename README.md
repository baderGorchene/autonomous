# BookSlot

BookSlot is a dead-simple booking page solution for local service businesses, designed to replace chaotic WhatsApp appointment management. It offers a shareable booking link, customer self-booking, and instant notifications for business owners. It is built with bilingual support (English + Arabic/French) to serve the MENA and North Africa markets.

## Features

- Owner signup and service setup
- Public, mobile-first booking page
- Time slot availability management (one-off and recurring)
- Email confirmation to both parties
- Simple dashboard for upcoming bookings and analytics
- Bilingual support (English, Arabic, French)
- Comprehensive error handling
- Stripe payment gateway for premium subscriptions
- Basic analytics (booking counts, popular services)
- Subscription management UI for owners
- Admin panel for managing owners, services, and bookings
- Customer accounts for managing their bookings and profiles
- Review and rating system for services
- SEO optimization for booking pages
- Performance optimization and caching
- Robust security measures

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python 3.9+
- pip (Python package installer)
- PostgreSQL database
- Redis server

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd bookslot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the project root based on `.env.example`. Replace placeholder values with your actual credentials and settings.
    ```dotenv
    # .env example
    SECRET_KEY="your_super_secret_key_for_jwt_signing"
    DATABASE_URL="postgresql://user:password@host:port/database_name"
    SENDGRID_API_KEY="your_sendgrid_api_key"
    TWILIO_ACCOUNT_SID="your_twilio_account_sid"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_PHONE_NUMBER="+1234567890" # Your Twilio phone number
    STRIPE_SECRET_KEY="sk_test_your_stripe_secret_key"
    STRIPE_WEBHOOK_SECRET="whsec_your_stripe_webhook_secret"
    APP_BASE_URL="http://localhost:8000"
    REDIS_URL="redis://localhost:6379/0"
    ```

5.  **Run database migrations:**
    ```bash
    alembic upgrade head
    ```

6.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be accessible at `http://localhost:8000`.

### Running Tests

To run the automated test suite:

```bash
pytest
```

### Security Scans

To perform automated security scans for dependency vulnerabilities and static code analysis:

1.  **Ensure security tools are installed:** They are included in `requirements.txt`.

2.  **Run the security scanning script:**
    ```bash
    chmod +x scripts/run_security_scans.sh
    ./scripts/run_security_scans.sh
    ```

    This script will execute:
    -   `pip-audit`: Scans `requirements.txt` for known vulnerabilities in your dependencies.
    -   `Bandit`: Performs static analysis on the `src` directory to find common security issues in Python code (e.g., hardcoded passwords, SQL injection risks, insecure use of standard library modules).

    Review the output of these scans and address any reported vulnerabilities or warnings.

    **Note:** Automated scans are a crucial part of security, but they do not replace comprehensive penetration testing or manual security audits by experts. For a complete security assessment, consider using Dynamic Application Security Testing (DAST) tools like OWASP ZAP or Burp Suite against the running application, and engaging in professional penetration testing services.

## Deployment

Deployment instructions will be detailed here, including Docker setup and environment configuration for production.

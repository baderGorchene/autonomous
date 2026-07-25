# BookSlot - Dead-Simple Booking Page for Local Service Businesses

BookSlot is a web application designed to provide a straightforward booking page for local service businesses such as salons, clinics, tutors, mechanics, and coaches. It aims to replace the manual appointment management often done through chaotic WhatsApp messages with a streamlined online booking system.

## Features

*   **Owner Signup & Service Setup**: Business owners can create an account, set up their business profile, define their services, and specify their availability.
*   **Public Booking Page**: Each owner gets a unique, shareable booking link (e.g., `bookslot.app/their-name`) where customers can easily book appointments without needing to create an account.
*   **Time Slot Availability**: Customers can see and select available time slots based on the owner's defined schedule.
*   **Email & WhatsApp Notifications**: Both the owner and the customer receive instant notifications (email and/or WhatsApp) with booking details upon successful reservation.
*   **Simple Dashboard**: Owners have access to a dashboard displaying their upcoming bookings.
*   **Bilingual Support**: The application supports English, Arabic, and French from day one to cater to the underserved MENA and North Africa markets.
*   **Mobile-First UI/UX**: The booking page and dashboard are designed with a mobile-first approach for optimal experience on any device.
*   **Error Handling**: Robust error handling for booking submissions and profile updates.

## Monetization

*   **Free Tier**: Up to 20 bookings per month.
*   **Premium Tier**: $19/month for unlimited bookings.

## Target Audience

Solo service providers who typically have 10-50 clients per week and are currently overwhelmed by managing appointments via direct messaging platforms.

## Technologies Used

*   **Backend**: FastAPI (Python)
*   **Database**: SQLAlchemy (SQLite for MVP, easily scalable)
*   **Frontend**: Jinja2 (templating), HTML5, CSS3 (Bootstrap 5 for UI/UX)
*   **Internationalization**: Babel, gettext
*   **Notifications**: SendGrid (email), Twilio (WhatsApp)
*   **Authentication**: JWT (JSON Web Tokens)
*   **Testing**: Pytest, httpx, respx
*   **Deployment**: Docker, Gunicorn/Uvicorn

## Setup and Installation

### Prerequisites

*   Python 3.8+
*   pip (Python package installer)
*   Docker (optional, for containerized deployment)

### Local Development

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
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

4.  **Set up environment variables:**
    Create a `.env` file in the project root based on `.env.example`. Fill in your API keys for SendGrid, Twilio, etc.
    ```dotenv
    SECRET_KEY="your-super-secret-key-replace-this"
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    SENDGRID_API_KEY="SG.YOUR_SENDGRID_API_KEY"
    TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
    TWILIO_WHATSAPP_NUMBER="+14155238886" # Your Twilio WhatsApp Sandbox number or approved number
    GEMINI_API_KEY="AIzaSyB-YOUR_GEMINI_API_KEY" # Not directly used in current MVP, but good to have
    ```

5.  **Run database migrations (if any, for SQLAlchemy models this is handled on app startup):**
    The `src/database.py` and `src/main.py` handle initial table creation. No explicit migration steps are needed for the current SQLite setup.

6.  **Compile translation files:**
    ```bash
    # First, extract translatable strings (only needed when adding/changing strings)
    # pybabel extract -F babel.cfg -o locales/messages.pot src templates
    # Then, initialize or update .po files (only needed once per language or after extraction)
    # pybabel init -i locales/messages.pot -d locales -l ar
    # pybabel init -i locales/messages.pot -d locales -l fr
    # pybabel update -i locales/messages.pot -d locales

    # Compile .po files to .mo files for use by gettext
    find locales -type d -name 'LC_MESSAGES' | xargs -I {} bash -c 'msgfmt {}.po -o {}.mo'
    ```
    *Note: `babel.cfg` is not included but would be needed for `pybabel extract`. For this exercise, `.po` files are provided directly.* Also, `msgfmt` might not be available by default in some environments. It's part of `gettext` utilities.

7.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    ```
    The application will be accessible at `http://127.0.0.1:8000`.

### Running Tests

```bash
pytest
```

### Docker Deployment

1.  **Build the Docker image:**
    ```bash
    docker build -t bookslot-app .
    ```

2.  **Run the Docker container:**
    ```bash
    docker run -d -p 8000:8000 --name bookslot bookslot-app
    ```

    Remember to provide environment variables to the container. You can pass them using `-e` flags or by mounting an `.env` file.
    ```bash
    docker run -d -p 8000:8000 --name bookslot \ 
        -e SECRET_KEY="your-secret-key" \ 
        -e SENDGRID_API_KEY="SG.YOUR_SENDGRID_API_KEY" \ 
        -e TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \ 
        -e TWILIO_AUTH_TOKEN="your_twilio_auth_token" \ 
        -e TWILIO_WHATSAPP_NUMBER="+14155238886" \ 
        bookslot-app
    ```

## Project Structure

```
.env.example
Dockerfile
README.md
requirements.txt
src/
├── __init__.py
├── config.py
├── crud.py
├── database.py
├── i18n_config.py
├── main.py
├── models.py
├── notifications.py
├── schemas.py
└── security.py
locales/
├── ar/
│   └── LC_MESSAGES/
│       └── messages.po
└── fr/
    └── LC_MESSAGES/
        └── messages.po
templates/
├── availability.html
├── base.html
├── booking_confirmation.html
├── booking_page.html
├── dashboard.html
├── index.html
├── login.html
├── profile.html
├── services.html
tests/
└── test_app.py
```

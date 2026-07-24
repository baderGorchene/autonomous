# BookSlot

BookSlot is a dead-simple booking page solution designed for local service businesses (salons, clinics, tutors, mechanics, coaches) who currently manage appointments via WhatsApp chaos. It provides a shareable link for owners, allows customers to book themselves easily, and notifies the owner via WhatsApp/email. No accounts are needed for customers.

## Business Idea & MVP Features

**Business Idea**: BookSlot aims to simplify appointment management for solo service providers (10-50 clients/week) who are overwhelmed by manual scheduling. It offers a straightforward $19/month subscription for unlimited bookings, with a free tier for up to 20 bookings/month.

**MVP Features**:
1.  **Owner Signup & Service Setup Page**: Owners can register and configure their services and availability.
2.  **Public Booking Page**: A mobile-first, user-friendly page for customers to view services and book appointments.
3.  **Time Slot Availability**: System manages and displays available booking slots.
4.  **Email Confirmation**: Automated email notifications to both the owner and the customer upon booking.
5.  **Simple Dashboard**: Owners can view their upcoming bookings and manage their profile.
6.  **Bilingual Support**: Fully localized in English, Arabic, and French from day one to target the MENA and North Africa markets.

## Technologies Used

*   **Backend**: FastAPI (Python)
*   **Database**: SQLite (for MVP), SQLAlchemy ORM
*   **Templating**: Jinja2
*   **Styling**: HTML/CSS (mobile-first design)
*   **Internationalization**: `gettext`
*   **Email Notifications**: SendGrid
*   **WhatsApp Notifications**: Twilio
*   **AI Integration**: Google Generative AI (for potential future enhancements)
*   **Testing**: Pytest

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in the root directory of the project based on `.env.example`:

```bash
cp .env.example .env
```

Edit the `.env` file with your actual credentials:

```ini
SECRET_KEY="your-super-secret-key-for-jwt"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
SENDGRID_API_KEY="your-sendgrid-api-key"
TWILIO_ACCOUNT_SID="your-twilio-account-sid"
TWILIO_AUTH_TOKEN="your-twilio-auth-token"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1XXXXXXXXXX" # Your Twilio WhatsApp enabled number
GEMINI_API_KEY="your-gemini-api-key"
```

### 4. Initialize the Database

The database (`bookslot.db`) will be created automatically when the application runs for the first time. You can also explicitly create tables using SQLAlchemy:

```python
# This is usually handled by the app's startup event,
# but for manual setup or migrations, you might run:
# from src.database import Base, engine
# from src.models import * # Import all models
# Base.metadata.create_all(bind=engine)
```

### 5. Run the Application

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be accessible at `http://localhost:8000`.

### 6. Running Tests

```bash
pytest
```

## Deployment

### Docker

A `Dockerfile` is provided to containerize the application.

1.  **Build the Docker image:**
    ```bash
    docker build -t bookslot .
    ```
2.  **Run the Docker container:**
    ```bash
    docker run -p 8000:8000 --env-file ./.env bookslot
    ```
    Ensure your `.env` file is properly configured with all necessary environment variables.

## Roadmap

Refer to the project roadmap for planned features and iterations.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

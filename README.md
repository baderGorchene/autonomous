# BookSlot

BookSlot is a dead-simple booking page solution for local service businesses to manage appointments without the WhatsApp chaos. It provides a shareable booking link, allows customers to self-book, and notifies the owner via WhatsApp/email. Designed to be bilingual (English + Arabic/French) from day one, targeting underserved markets.

## Features

-   **Owner Signup & Service Setup**: Business owners can register, define their services, and set up their availability.
-   **Public Booking Page**: A mobile-first, beautiful booking page for customers to easily schedule appointments.
-   **Time Slot Availability**: Customers can see and select available time slots.
-   **Email Confirmations**: Automated email notifications for both the owner and the customer upon booking.
-   **Owner Dashboard**: A simple dashboard for owners to view upcoming bookings and manage their profile.
-   **Bilingual Support**: Full support for English, Arabic, and French, with a language toggle.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

-   Python 3.9+
-   pip

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/bookslot.git
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
    Create a `.env` file in the project root with the following variables:
    ```
    SECRET_KEY="your-super-secret-key"
    SENDGRID_API_KEY="your-sendgrid-api-key"
    TWILIO_ACCOUNT_SID="your-twilio-account-sid"
    TWILIO_AUTH_TOKEN="your-twilio-auth-token"
    TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp enabled number
    GEMINI_API_KEY="your-gemini-api-key" # Placeholder for future AI features
    ```

5.  **Initialize the database:**
    The application uses SQLite, and the database will be created automatically on first run. You can run migrations if you set up Alembic (not included in MVP).

6.  **Run the application:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

### Running Tests

```bash
pytest
```

## Deployment

A basic `Dockerfile` is provided for containerization.

```bash
docker build -t bookslot .
docker run -p 8000:8000 bookslot
```

Remember to configure environment variables for production deployments.

## Built With

-   [FastAPI](https://fastapi.tiangolo.com/) - The web framework used
-   [SQLAlchemy](https://www.sqlalchemy.org/) - SQL toolkit and Object Relational Mapper
-   [Jinja2](https://jinja.palletsprojects.com/) - Templating engine
-   [Pydantic](https://pydantic.dev/) - Data validation and settings management
-   [SendGrid](https://sendgrid.com/) - Email service
-   [Twilio](https://www.twilio.com/) - SMS/WhatsApp service

## License

This project is licensed under the MIT License - see the LICENSE.md file for details (not yet created, but a standard placeholder).

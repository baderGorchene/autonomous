# BookSlot

BookSlot is a dead-simple, bilingual (English, Arabic, French) booking page solution designed for local service businesses. It helps solo service providers manage appointments without the chaos of WhatsApp messages, offering a streamlined booking experience for both business owners and their clients.

## Business Idea

**Problem:** Local service businesses (salons, clinics, tutors, mechanics, coaches) often manage appointments through WhatsApp, leading to disorganization, missed bookings, and constant back-and-forth messaging.

**Solution:** BookSlot provides a dedicated, shareable booking page (`bookslot.app/their-name`) where customers can self-book appointments. The owner receives instant notifications via WhatsApp/email, and customers don't need to create accounts.

**Target Market:** Solo service providers with 10-50 clients/week who are overwhelmed by manual appointment scheduling.

**Key Features (MVP):**
1.  **Owner Signup & Service Setup:** Business owners can register, define their services, and set their availability.
2.  **Public Booking Page:** A mobile-first, beautiful, and shareable link for customers to book services.
3.  **Time Slot Availability:** Customers can see and select available time slots.
4.  **Email Confirmations:** Automated email confirmations sent to both the owner and the customer upon booking.
5.  **Simple Dashboard:** Owners get a dashboard to view upcoming bookings and manage their profile.
6.  **Bilingual Support:** English, Arabic, and French languages available from day one, targeting underserved MENA and North Africa markets.

**Monetization:**
*   Free for up to 20 bookings/month.
*   $19/month for unlimited bookings.

## Features

*   **User Authentication:** Secure owner login and registration.
*   **Service Management:** Owners can add, edit, and delete their services.
*   **Availability Configuration:** Flexible setup for working hours and breaks.
*   **Public Booking Page:** Responsive design, intuitive booking flow.
*   **Booking Confirmation:** Email notifications for both parties.
*   **Owner Dashboard:** Overview of upcoming appointments.
*   **Internationalization (i18n):** Full support for English, Arabic, and French.
*   **Robust Backend:** Built with FastAPI, SQLAlchemy, and Pydantic.
*   **Notifications:** Integrated with SendGrid (email) and Twilio (WhatsApp).

## Technologies Used

*   **Backend:** Python, FastAPI
*   **Database:** SQLAlchemy (ORM), SQLite (development), PostgreSQL (production)
*   **Frontend:** HTML, CSS (TailwindCSS or similar for styling, though not explicitly defined, responsive design is a focus), Jinja2 (templating)
*   **Authentication:** JWT (JSON Web Tokens)
*   **Internationalization:** Babel
*   **Notifications:** SendGrid (email), Twilio (WhatsApp)
*   **Deployment:** Docker, Gunicorn

## Setup and Local Development

### Prerequisites

*   Python 3.11+
*   `pip` (Python package installer)
*   `git` (for cloning the repository)

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/bookslot.git # Replace with actual repo URL
cd bookslot
```

### 2. Create a Virtual Environment

It's highly recommended to use a virtual environment to manage dependencies.

```bash
python -m venv venv
source venv/bin/activate # On Windows: .\venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Create a `.env` file in the project root directory based on `example.env`.

```bash
cp example.env .env
```

Edit the `.env` file with your specific configurations. For local development, `DATABASE_URL` can remain `sqlite:///./sql_app.db`. You will need actual API keys for SendGrid and Twilio to test notifications.

```dotenv
# .env file
SECRET_KEY="your-super-secret-key-for-development"
DATABASE_URL="sqlite:///./sql_app.db"

SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY"
TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID"
TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN"
TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" # Your Twilio WhatsApp number
```

### 5. Initialize the Database

The application uses SQLAlchemy to manage the database schema.

```bash
python -c "from src.database import create_tables; create_tables()"
```

This will create `sql_app.db` in your project root if you're using SQLite.

### 6. Run the Application

```bash
uvicorn src.main:app --reload --port 8000
```

The application will be accessible at `http://127.0.0.1:8000`. The `--reload` flag is useful for development as it restarts the server on code changes.

### 7. Accessing the Application

*   **Owner Signup/Login:** `http://127.0.0.1:8000/owner/signup` or `http://127.0.0.1:8000/owner/login`
*   **Owner Dashboard:** `http://127.0.0.1:8000/dashboard` (requires login)
*   **Public Booking Page:** `http://127.0.0.1:8000/book/{owner_slug}` (e.g., `http://127.0.0.1:8000/book/john-doe`)

## Internationalization (i18n)

BookSlot supports English, Arabic, and French.

### How to add/update translations

1.  **Extract new strings:**
    ```bash
pybabel extract -F babel.cfg -o locales/messages.pot src templates
    ```
    (You might need to create a `babel.cfg` file first, see example below)

2.  **Update existing language catalogs:**
    ```bash
pybabel update -i locales/messages.pot -d locales -l ar
pybabel update -i locales/messages.pot -d locales -l fr
    ```

3.  **Translate strings:** Open the `.po` files (`locales/ar/LC_MESSAGES/messages.po`, `locales/fr/LC_MESSAGES/messages.po`) in a text editor or a PO editor (like Poedit) and add translations.

4.  **Compile translations:**
    ```bash
pybabel compile -d locales
    ```

### `babel.cfg` example:

```ini
[python: src/**.py]
[jinja2: templates/**.html]
extensions=jinja2.ext.with_,jinja2.ext.autoescape,jinja2.ext.do,jinja2.ext.loopcontrols
```

## Running Tests

```bash
pytest
```

Ensure all dependencies from `requirements.txt` are installed.

## Deployment

### Production Environment Variables

For production, it's crucial to set environment variables securely.

*   `SECRET_KEY`: Generate a strong, random key.
*   `DATABASE_URL`: Use a robust database like PostgreSQL. Example: `postgresql://user:password@host:port/dbname`
*   `SENDGRID_API_KEY`: Your production SendGrid API key.
*   `TWILIO_ACCOUNT_SID`: Your production Twilio Account SID.
*   `TWILIO_AUTH_TOKEN`: Your production Twilio Auth Token.
*   `TWILIO_WHATSAPP_NUMBER`: Your production Twilio WhatsApp number.
*   `WEB_CONCURRENCY`: Number of Gunicorn workers (e.g., `2 * CPU_CORES + 1`).
*   `LOG_LEVEL`: `info`, `warning`, `error`, `debug`.

### Docker Deployment

The recommended way to deploy BookSlot is using Docker.

1.  **Build the Docker image:**

    ```bash
docker build -t bookslot:latest .
    ```

2.  **Run the Docker container:**

    ```bash
docker run -d --name bookslot_app \
        -p 80:8000 \
        -e SECRET_KEY="YOUR_PRODUCTION_SECRET_KEY" \
        -e DATABASE_URL="postgresql://user:password@host:port/dbname" \
        -e SENDGRID_API_KEY="YOUR_SENDGRID_API_KEY" \
        -e TWILIO_ACCOUNT_SID="YOUR_TWILIO_ACCOUNT_SID" \
        -e TWILIO_AUTH_TOKEN="YOUR_TWILIO_AUTH_TOKEN" \
        -e TWILIO_WHATSAPP_NUMBER="whatsapp:+1234567890" \
        bookslot:latest
    ```
    **Note:** For production, you would typically use a separate PostgreSQL container or a managed database service, and link them or configure the `DATABASE_URL` accordingly.

### Gunicorn Configuration

The `gunicorn_conf.py` file provides production-ready settings for Gunicorn workers, logging, and timeouts. Ensure it's configured appropriately for your server's resources.

### Database Migrations (Future Enhancement)

For managing database schema changes in production, consider integrating a tool like `Alembic`. This MVP does not include explicit migration scripts, relying on `create_tables()` for initial setup.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

This project is licensed under the MIT License. (Or specify your chosen license)

---

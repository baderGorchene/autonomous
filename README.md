# BookSlot

**A dead-simple $19/month booking page for local service businesses.**

BookSlot aims to eliminate the WhatsApp chaos for solo service providers by offering a streamlined, shareable booking page.
Customers can self-book, and owners receive instant notifications, all without requiring customer accounts.

## 
Business Idea

Local service businesses (salons, clinics, tutors, mechanics, coaches) often manage appointments through chaotic WhatsApp messages. BookSlot provides a simple, affordable solution:

*   **Shareable Link:** Owners get a unique link (e.g., `bookslot.app/their-name`).
*   **Self-Booking:** Customers book appointments themselves.
*   **Instant Notifications:** Owners receive WhatsApp/email notifications with booking details.
*   **No Customer Accounts:** Frictionless experience for customers.
*   **Bilingual Support:** English + Arabic/French from day one, targeting underserved MENA and North Africa markets.

## 
MVP Features

1.  **Owner Signup & Service Setup:** Business owners can create an account, define their services, and set up their availability.
2.  **Public Booking Page:** A mobile-first, beautiful page for customers to view services and book slots.
3.  **Time Slot Availability:** Owners can specify available time slots.
4.  **Email Confirmation:** Automated email confirmations sent to both the owner and the customer upon booking.
5.  **Simple Dashboard:** Owners can view upcoming bookings and manage their profile.

## 
Monetization

*   **Free Tier:** Up to 20 bookings/month.
*   **Premium Tier:** $19/month for unlimited bookings.

**Target Audience:** Solo service providers with 10-50 clients/week who are overwhelmed by WhatsApp appointment management.

## 
Technologies Used

*   **Backend:** FastAPI (Python)
*   **Database:** SQLite (development), PostgreSQL (production)
*   **ORM:** SQLAlchemy
*   **Templating:** Jinja2
*   **Styling:** CSS (custom, responsive)
*   **Email Notifications:** SendGrid
*   **WhatsApp Notifications:** Twilio
*   **Internationalization:** `gettext`
*   **Deployment:** Docker, Gunicorn, Uvicorn, Kubernetes (planned)
*   **Testing:** Pytest

## 
Setup (Local Development)

### Prerequisites

*   Python 3.12+
*   `pip`
*   `git`

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/bookslot.git
cd bookslot
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate # On Windows: .\venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Create a `.env` file in the project root based on `.env.example` and fill in your credentials:

```bash
cp .env.example .env
```
Edit `.env` with your specific values. `DATABASE_URL` can be `sqlite:///./sql_app.db` for local development.

### 5. Database Setup (Initial)

For local development with SQLite, the database will be created automatically.
For production, you'll need to set up a PostgreSQL database.

_**Future:** Database migrations will be handled using Alembic. For now, ensure your `src/models.py` schema matches your database._

### 6. Run the Application

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```
The application will be accessible at `http://localhost:8000`.

## 
Running Tests

```bash
pytest
```

## 
Internationalization

The application supports English, Arabic, and French. You can toggle the language on the public booking page and owner dashboard. Translation files are located in the `locales/` directory.

## 
Deployment (Production)

### 1. Docker Build

Ensure you have Docker installed.

```bash
docker build -t bookslot:latest .
```

### 2. Running with Docker & Gunicorn

For production, it's recommended to run the application using Gunicorn with a `uvicorn.workers.UvicornWorker`. The `Dockerfile` is configured to use `gunicorn.conf.py`.

```bash
# Ensure your .env file is correctly configured for production settings
# For example, DATABASE_URL should point to your production PostgreSQL instance.
docker run -p 8000:8000 --env-file ./.env bookslot:latest
```
Replace `.env` with your production environment file.

### 3. Environment Variables

In a production environment, it's best practice to pass environment variables directly to your container orchestration system (e.g., Kubernetes, Docker Compose, systemd) rather than relying on an `.env` file inside the container.

### 4. Database Migrations

_**Note:** This project is designed for future integration with Alembic for robust database migrations. For initial deployments, ensure your database schema is created manually or via `Base.metadata.create_all(engine)` in a setup script._

### 5. Kubernetes Deployment (Example)

An example Kubernetes Deployment and Service configuration is provided for reference:

```yaml
# See the 'gunicorn' section in the live documentation for example Kubernetes YAMLs.
# You will need to adapt these to your specific cluster and image registry.
```

## 
Contact

For support or inquiries, please contact [your-email@example.com](mailto:your-email@example.com).

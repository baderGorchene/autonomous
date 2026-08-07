# Use a slim Python image for smaller size
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application code
COPY . .

# Create database tables on startup (for SQLite, this will create the file)
# For production with PostgreSQL, you might run migrations separately or use a proper ORM migration tool.
# For this simple MVP, we can create tables on startup if they don't exist.
# This assumes src/database.py's create_tables() can be called safely multiple times.
RUN python -c "from src.database import create_tables; create_tables()"

# Expose the port the application runs on
EXPOSE 8000

# Command to run the application using Uvicorn with Gunicorn for production
CMD ["gunicorn", "src.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
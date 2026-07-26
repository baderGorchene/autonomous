# Use an official Python runtime as a parent image
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for gettext and psycopg2
RUN apt-get update && apt-get install -y \
    gettext \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Compile translations
# This step assumes that .po files are in locales/<lang>/LC_MESSAGES/
# and will compile them into .mo files.
RUN find locales -name "*.po" -execdir msgfmt -o {}.mo {} \;

# Expose port 8000 for the FastAPI application
EXPOSE 8000

# Run gunicorn with uvicorn workers
# CMD ["gunicorn", "src.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
# For development/testing, uvicorn directly might be easier
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

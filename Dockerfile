# Use an official Python runtime as a parent image
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for gettext and others
RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application using Gunicorn
# The `main` module is expected inside the `src` directory, so `src.main:app` is correct.
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "src.main:app"]
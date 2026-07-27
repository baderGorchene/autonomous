# Use an official Python runtime as a parent image
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for gettext (for .po file compilation)
# and potentially other libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the working directory
COPY . .

# Compile translation files
# This assumes that the `locales` directory is at the root of the /app (PROJECT_ROOT)
# and that `babel` is installed via requirements.txt
RUN python -m babel compile -d locales

# Expose the port the app runs on
EXPOSE 8000

# Run the application using Gunicorn
# Using 4 workers (a common recommendation is 2-4 * CPU cores) and binding to 0.0.0.0
# The --timeout 120 is for potentially long-running requests, adjust as needed.
CMD ["gunicorn", "src.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120"]

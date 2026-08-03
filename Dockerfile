# Use an official Python runtime as a parent image
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install gettext for locale compilation (needed for i18n)
RUN apt-get update && apt-get install -y gettext && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Compile translation files
# This assumes babel is installed via requirements.txt
# And that babel.cfg is present if needed for extraction, but for compilation only, it's usually fine.
RUN python -m babel compile -d locales

# Expose the port the app runs on
EXPOSE 8000

# Run the application using Uvicorn
# Use gunicorn with uvicorn workers for production for better performance and robustness
# Example: gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.main:app --bind 0.0.0.0:8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

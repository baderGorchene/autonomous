# Use an official Python runtime as a parent image
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install gettext for i18n compilation
RUN apt-get update && apt-get install -y gettext

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Compile translation files
RUN find locales -type d -name 'LC_MESSAGES' | xargs -I {} bash -c 'msgfmt {}.po -o {}.mo || true'

# Expose the port the app runs on
EXPOSE 8000

# Run the application using Gunicorn for production
# CMD ["gunicorn", "src.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
# For development/testing, you might use uvicorn directly:
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

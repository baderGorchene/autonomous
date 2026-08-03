# Use an official Python runtime as a parent image
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for gettext (msgfmt)
RUN apt-get update && apt-get install -y gettext && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Compile message catalogs for i18n
# This assumes 'locales' directory exists in the root of the project
# and contains 'ar', 'fr', 'en' subdirectories with LC_MESSAGES/messages.po
RUN for lang_dir in locales/*; do \
    if [ -d "$lang_dir/LC_MESSAGES" ]; then \
        lang=$(basename "$lang_dir"); \
        mkdir -p "$lang_dir/LC_MESSAGES"; \
        if [ -f "$lang_dir/LC_MESSAGES/messages.po" ]; then \
            msgfmt -o "$lang_dir/LC_MESSAGES/messages.mo" "$lang_dir/LC_MESSAGES/messages.po"; \
        else \
            echo "Warning: messages.po not found for language $lang, creating dummy .mo"; \
            touch "$lang_dir/LC_MESSAGES/messages.mo"; \
        fi; \
    fi; \
done


# Expose the port the app runs on
EXPOSE 8000

# Run the application with Gunicorn
# Using 4 workers, binding to all interfaces, and running the FastAPI app
CMD ["gunicorn", "src.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]

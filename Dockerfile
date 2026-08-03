# Use an official Python runtime as a parent image
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies needed for gettext (for .mo file compilation)
# and potentially other libraries (e.g., cryptography for python-jose)
RUN apt-get update && apt-get install -y \
    gettext \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Compile .po files to .mo files for gettext
# Ensure babel.cfg is present or adjust command if not using babel for compilation
# For simplicity, we'll assume `pybabel compile` is run if .po files change.
# For a full CI/CD, this step would be more robust.
# For now, rely on `python-gettext`'s runtime loading, or ensure .mo files are pre-compiled.
# If babel is installed and babel.cfg is present, this would be:
# RUN pybabel compile -d locales

# Expose port 8000 for the FastAPI application
EXPOSE 8000

# Run the application using Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

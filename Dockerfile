# Stage 1: Build dependencies
FROM python:3.11-slim-buster AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Final image
FROM python:3.11-slim-buster

WORKDIR /app

# Install runtime dependencies
COPY --from=builder /app/wheels /wheels
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/gunicorn
RUN pip install --no-cache-dir /wheels/*

# Copy application code
COPY ./src /app/src
COPY ./templates /app/templates
COPY ./locales /app/locales
COPY gunicorn_conf.py /app/gunicorn_conf.py

# Create a non-root user
RUN adduser --system --group appuser
USER appuser

# Expose the port Gunicorn will listen on
EXPOSE 8000

# Command to run the application using Gunicorn
# Using gunicorn_conf.py for configuration
CMD ["gunicorn", "src.main:app", "-c", "gunicorn_conf.py"]

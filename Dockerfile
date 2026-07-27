FROM python:3.12 AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy the core application files and assets
COPY src src
COPY templates templates
COPY locales locales
COPY static static
COPY .env.example .env.example
COPY README.md README.md
COPY requirements.txt requirements.txt
COPY gunicorn.conf.py gunicorn.conf.py

# Command to run gunicorn with the config file
CMD ["gunicorn", "-c", "gunicorn.conf.py", "src.main:app"]

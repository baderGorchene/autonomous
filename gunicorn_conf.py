import os

# Gunicorn configuration file

# Bind to 0.0.0.0 to make it accessible from outside the container
bind = "0.0.0.0:8000"

# Number of worker processes. A common formula is (2 * CPU_CORES) + 1.
# Adjust based on your server's CPU and expected load.
workers = int(os.environ.get("WEB_CONCURRENCY", 2))

# Worker class for FastAPI (ASGI application)
worker_class = "uvicorn.workers.UvicornWorker"

# Log level
loglevel = os.environ.get("LOG_LEVEL", "info")

# Access log file
accesslog = "-"  # Output to stdout
errorlog = "-"   # Output to stderr

# Timeout for workers (in seconds)
timeout = 120

# Max requests a worker will process before restarting
max_requests = 1000
max_requests_jitter = 50

# Preload application for faster restarts (might consume more memory)
preload_app = False # Set to True if application setup is lightweight and memory allows

# Daemonize the Gunicorn process (usually False for containerized apps)
daemon = False

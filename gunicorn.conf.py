# gunicorn.conf.py
worker_class = "uvicorn.workers.UvicornWorker"
workers = 4
threads = 1
bind = "0.0.0.0:8000"
timeout = 120
keepalive = 5
loglevel = "info"
accesslog = "-"
errorlog = "-"

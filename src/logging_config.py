import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Ensure logs directory exists
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Main application logger
    app_logger = logging.getLogger("bookslot.app")
    app_logger.setLevel(getattr(logging, log_level))
    app_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # File handler for general logs
    app_file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=10485760, backupCount=5 # 10MB, 5 backups
    )
    app_file_handler.setFormatter(app_formatter)
    app_logger.addHandler(app_file_handler)

    # Console handler
    app_console_handler = logging.StreamHandler()
    app_console_handler.setFormatter(app_formatter)
    app_logger.addHandler(app_console_handler)

    # Security logger
    security_logger = logging.getLogger("bookslot.security")
    security_logger.setLevel(logging.WARNING) # Log security events at WARNING level or higher
    security_formatter = logging.Formatter("%(asctime)s - SECURITY - %(levelname)s - %(message)s")
    security_file_handler = RotatingFileHandler(
        os.path.join(log_dir, "security.log"), maxBytes=10485760, backupCount=5
    )
    security_file_handler.setFormatter(security_formatter)
    security_logger.addHandler(security_file_handler)
    security_logger.propagate = False # Prevent security logs from going to app.log again if not desired

    # Silence uvicorn access logs if not needed for production or debug
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # Set root logger level to capture everything, handlers will filter
    logging.getLogger().setLevel(logging.INFO)

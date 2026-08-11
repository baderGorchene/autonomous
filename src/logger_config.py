import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    app_logger = logging.getLogger("app_logger")
    app_logger.setLevel(logging.INFO)

    app_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(app_formatter)
    app_logger.addHandler(console_handler)

    app_file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    app_file_handler.setFormatter(app_formatter)
    app_logger.addHandler(app_file_handler)

    security_logger = logging.getLogger("security_logger")
    security_logger.setLevel(logging.INFO)

    security_formatter = logging.Formatter(
        "%(asctime)s - SECURITY - %(levelname)s - %(message)s"
    )

    security_file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "security.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3
    )
    security_file_handler.setFormatter(security_formatter)
    security_logger.addHandler(security_file_handler)

    app_logger.propagate = False
    security_logger.propagate = False

    return app_logger, security_logger

app_logger, security_logger = setup_logging()

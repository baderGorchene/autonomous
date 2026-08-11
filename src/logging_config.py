import logging
import sys

def setup_security_logging():
    security_logger = logging.getLogger('security_events')
    security_logger.setLevel(logging.INFO)

    # Prevent adding multiple handlers if function is called multiple times
    if not security_logger.handlers:
        # File handler for security events
        file_handler = logging.FileHandler('security_events.log')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        security_logger.addHandler(file_handler)

        # Console handler for security events (optional, for immediate visibility)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - SECURITY - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        security_logger.addHandler(console_handler)

    return security_logger

security_logger = setup_security_logging()

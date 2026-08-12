import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Application Logger
app_logger = logging.getLogger("bookslot_app")
app_logger.setLevel(logging.INFO)
app_file_handler = RotatingFileHandler(os.path.join(LOG_DIR, "app.log"), maxBytes=10 * 1024 * 1024, backupCount=5) # 10MB, 5 backups
app_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
app_file_handler.setFormatter(app_formatter)
app_logger.addHandler(app_file_handler)

# Security Logger
security_logger = logging.getLogger("bookslot_security")
security_logger.setLevel(logging.INFO) # Use INFO for successful, WARNING for failed/suspicious
sec_file_handler = RotatingFileHandler(os.path.join(LOG_DIR, "security.log"), maxBytes=10 * 1024 * 1024, backupCount=5)
# Custom formatter to include client_ip and user_id from extra dict
sec_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - IP:%(client_ip)s - User:%(user_id)s - %(message)s")
sec_file_handler.setFormatter(sec_formatter)
security_logger.addHandler(sec_file_handler)

# Console Handler for both (optional, useful for development)
console_handler = logging.StreamHandler()
console_handler.setFormatter(app_formatter) # Use app formatter for console output
app_logger.addHandler(console_handler)
security_logger.addHandler(console_handler)

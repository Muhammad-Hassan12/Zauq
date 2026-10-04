import os
import logging
from logging.handlers import RotatingFileHandler


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        from backend.security.sanitizer import sanitize_secrets
        return sanitize_secrets(super().format(record))

def setup_logging(log_level: int = logging.INFO):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "zauq.log")

    formatter = RedactingFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid adding duplicate handlers if already configured
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

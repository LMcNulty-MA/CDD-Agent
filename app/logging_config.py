# app/logging_config.py
import logging

from app.config import settings

def configure_logging():
    # Use log level from settings if available, otherwise default to INFO
    log_level = getattr(settings, 'LOG_LEVEL', 'INFO')
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Use log format from settings if available
    log_format = getattr(settings, 'LOG_FORMAT', "%(asctime)s - %(levelname)s - %(name)s - %(message)s")

    logging.basicConfig(
        level=log_level,
        format=log_format
    )

    # Suppress DEBUG logs from external libraries
    for logger_name in [
        'botocore', 'aiobotocore', 'pymongo', 'openai', 'httpcore', 'httpx',
        'urllib3', 'boto3', 's3transfer', 'motor'
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Ensure app loggers respect configured level
    logging.getLogger('app').setLevel(log_level) 
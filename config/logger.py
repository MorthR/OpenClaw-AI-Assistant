import logging
import sys

def setup_logger():
    logger = logging.getLogger("OpenClaw")
    logger.setLevel(logging.INFO)

    # Avoid adding handlers repeatedly
    if logger.handlers:
        return logger

    # Log format: Timestamp - Log Level - Module - Message
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (Prints to terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (Saves to local app.log)
    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()
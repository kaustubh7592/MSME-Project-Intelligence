import logging

LOGGER_NAME = "msmeintel"


def configure_logging(level: str) -> logging.Logger:
    """Configure the application logger once and update its level."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    return logger

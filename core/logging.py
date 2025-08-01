import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("fastapi_logger")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler("server.log", maxBytes=1000000, backupCount=3)
formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")

handler.setFormatter(formatter)
logger.addHandler(handler) 
import logging, os

def get_logger():
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("agent")
    if not logger.handlers:
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
        logger.addHandler(logging.FileHandler("logs/agent.jsonl"))
        logger.addHandler(logging.StreamHandler())
    return logger

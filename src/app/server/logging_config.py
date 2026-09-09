import logging
import sys
from pythonjsonlogger import jsonlogger

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        from app.server.context import get_correlation_id
        record.correlation_id = get_correlation_id() or "N/A"
        return True

def configure_logging():
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s')
    logHandler.setFormatter(formatter)
    
    correlation_filter = CorrelationIdFilter()
    logHandler.addFilter(correlation_filter)
    
    logger.addHandler(logHandler)
    logger.setLevel(logging.INFO)
    
    # Access logs stay on: they are the primary record of who called what, and
    # silencing them removed the only request-level audit trail. Set
    # ACCESS_LOG_LEVEL=WARNING to quieten them in a noisy local environment.
    import os

    access_level = os.environ.get("ACCESS_LOG_LEVEL", "INFO").upper()
    logging.getLogger("uvicorn.access").setLevel(getattr(logging, access_level, logging.INFO))

    # These are genuinely noisy and carry no audit value.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

import logging
import json
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "time": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        })


def setup_logger():
    logger = logging.getLogger("companion")
    logger.setLevel(logging.DEBUG)

    # file handler — rotates daily
    from logging.handlers import TimedRotatingFileHandler
    fh = TimedRotatingFileHandler(
        LOG_DIR / "companion.log",
        when="midnight",
        backupCount=7,
    )
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)

    # console handler
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(module)s] %(message)s"))
    logger.addHandler(ch)

    return logger


log = setup_logger()
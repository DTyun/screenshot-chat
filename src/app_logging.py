"""UTF-8 rotating diagnostics, separate from users' message content."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger('screenshot_chat')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(logging.NullHandler())


def configure_logging(root):
    path = Path(root)/'app.log'
    handler = RotatingFileHandler(path,maxBytes=2*1024*1024,backupCount=2,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',datefmt='%Y-%m-%d %H:%M:%S'))
    close_logging()
    logger.addHandler(handler)
    return path


def close_logging():
    for handler in list(logger.handlers):
        if isinstance(handler,RotatingFileHandler):
            logger.removeHandler(handler)
            handler.close()


def active_log_path(root):
    for handler in logger.handlers:
        if isinstance(handler,RotatingFileHandler):
            return Path(handler.baseFilename)
    return Path(root)/'app.log'


def read_log_tail(path,limit=512*1024):
    """Bound memory and discard a partial first line when reading a large log."""
    try:
        with Path(path).open('rb') as stream:
            size = stream.seek(0,2)
            truncated = size>limit
            stream.seek(max(0,size-limit))
            data = stream.read(limit)
    except FileNotFoundError:
        return '',False
    if truncated and b'\n' in data:
        data = data.split(b'\n',1)[1]
    return data.decode('utf-8',errors='replace'),truncated

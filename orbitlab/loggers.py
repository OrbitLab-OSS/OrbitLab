"""OrbitLab logging."""

import functools
import logging
import logging.handlers
from pathlib import Path

from orbitlab.web.utilities import is_production


class OrbitLabLogger:
    """Central logging configuration for OrbitLab."""

    DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    DEFAULT_BACKUP_COUNT = 7

    def __init__(self) -> None:
        """Initialize OrbitLab Logging Manager."""
        self.log_dir = Path("/var/log/orbitlab") if is_production() else Path().cwd() / "TEST_ROOT" / "logs"
        self.log_level = logging.INFO if is_production() else logging.DEBUG
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.formatter = logging.Formatter(fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    def _create_handler(self, filename: Path) -> logging.Handler:
        handler = logging.handlers.RotatingFileHandler(
            filename=filename,
            maxBytes=self.DEFAULT_MAX_BYTES,
            backupCount=self.DEFAULT_BACKUP_COUNT,
        )
        handler.setLevel(level=self.log_level)
        handler.setFormatter(fmt=self.formatter)
        return handler

    def get_logger(self, name: str, filename: Path) -> logging.Logger:
        """Return a configured logger."""
        logger = logging.getLogger(name=name)
        logger.setLevel(level=self.log_level)
        logger.propagate = False

        handler = self._create_handler(filename=filename)
        logger.addHandler(hdlr=handler)
        return logger


# Create singleton instance at import time
_logging_manager = OrbitLabLogger()

@functools.lru_cache(maxsize=10)
def get_client_logger(client: str) -> logging.Logger:
    """Return a logger configured for the specified client."""
    filename = _logging_manager.log_dir / "clients" / f"{client.lower()}.log"
    filename.parent.mkdir(parents=True, exist_ok=True)
    return _logging_manager.get_logger(name=client, filename=filename)

@functools.lru_cache(maxsize=1)
def get_application_logger() -> logging.Logger:
    """Return a logger configured for the OrbitLab application."""
    filename = _logging_manager.log_dir / "application.log"
    return _logging_manager.get_logger(name="OrbitLab", filename=filename)

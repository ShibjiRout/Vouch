"""Logging setup. Called once at startup by the API and by the worker.

Stdlib logging, not loguru — loguru is only present as a transitive
dependency of fastembed, and building on someone else's dependency
means it can disappear on an upgrade.

Everything goes to stdout. Container platforms collect stdout, so no
file handlers and no rotation to maintain.

**Never log a key, a token, or a full chunk of document text.**
Log identifiers and counts.
"""

import logging
import os
import sys

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Libraries that log every HTTP call at INFO and drown everything else.
_NOISY = ("httpx", "httpcore", "urllib3", "qdrant_client", "openai", "filelock")


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. uvicorn --reload re-import)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)-24s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.setLevel(LOG_LEVEL)
    root.addHandler(handler)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

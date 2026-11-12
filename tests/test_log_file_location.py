"""The app log goes to data/logs/storyforge.log, not the working directory.

In the Docker image the working directory (/app) belongs to root and only
/app/data is writable, so a log opened relative to the CWD would crash startup.
"""

import io
import logging
import logging.handlers
from pathlib import Path

import pytest

from services.infra.structured_logger import configure_logging


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    yield
    for handler in root.handlers:
        if handler in saved_handlers:
            continue
        if isinstance(handler, logging.FileHandler):
            handler.close()
        elif isinstance(getattr(handler, "stream", None), io.TextIOWrapper):
            # configure_logging wraps sys.stdout.buffer; detach so garbage
            # collecting the wrapper does not close pytest's capture buffer.
            handler.stream.detach()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _file_handlers():
    return [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]


def test_log_file_is_created_under_missing_directory(tmp_path, restore_root_logging):
    log_file = tmp_path / "data" / "logs" / "storyforge.log"

    configure_logging(log_file=log_file)
    logging.getLogger("storyforge.test").info("hello log file")
    for handler in _file_handlers():
        handler.flush()

    assert "hello log file" in log_file.read_text(encoding="utf-8")


def test_log_file_rotates_and_is_the_only_file_handler(tmp_path, restore_root_logging):
    log_file = tmp_path / "logs" / "storyforge.log"

    configure_logging(log_file=log_file)

    handlers = _file_handlers()
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.handlers.RotatingFileHandler)
    assert handlers[0].maxBytes == 10 * 1024 * 1024
    assert Path(handlers[0].baseFilename) == log_file.resolve()


def test_app_logs_under_data_logs():
    import app

    repo_root = Path(app.__file__).resolve().parent
    assert app.LOG_FILE == repo_root / "data" / "logs" / "storyforge.log"

"""
Config-based logging module for different log levels
"""

from .config import get_config

_LOG_LEVEL_WARNING = 0
_LOG_LEVEL_INFO = 1
_LOG_LEVEL_DEBUG = 2


def current_log_level():
    """
    Determine current log level from the config
    """
    current = get_config("log_level").lower()
    if current == "debug":
        return _LOG_LEVEL_DEBUG
    if current == "info":
        return _LOG_LEVEL_INFO
    if current == "warning":
        return _LOG_LEVEL_WARNING
    return _LOG_LEVEL_WARNING


def warning(log):
    """
    Print warning messages
    """
    if current_log_level() >= _LOG_LEVEL_WARNING:
        print(f"[WARN] {log}")


def info(log):
    """
    Print info messages
    """
    if current_log_level() >= _LOG_LEVEL_INFO:
        print(f"[INFO] {log}")


def debug(log):
    """
    Print debug messages
    """
    if current_log_level() >= _LOG_LEVEL_DEBUG:
        print(f"[DEBUG] {log}")

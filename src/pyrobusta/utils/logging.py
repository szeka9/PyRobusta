"""
Config-based logging module for different log levels
"""

from pyrobusta.utils.config import get_config, CONF_LOG_LEVEL
from pyrobusta.utils.clock import ticks_ms

_LOG_LEVEL_OFF = -1  # Disable all logging
_LOG_LEVEL_ERROR = 0
_LOG_LEVEL_WARNING = 1
_LOG_LEVEL_INFO = 2
_LOG_LEVEL_DEBUG = 3


def current_log_level():
    """
    Determine current log level from the config.
    """
    current = get_config(CONF_LOG_LEVEL)
    if current == "off":
        return _LOG_LEVEL_OFF
    if current == "error":
        return _LOG_LEVEL_ERROR
    if current == "warning":
        return _LOG_LEVEL_WARNING
    if current == "info":
        return _LOG_LEVEL_INFO
    if current == "debug":
        return _LOG_LEVEL_DEBUG
    return _LOG_LEVEL_WARNING


def error(fmt, *args):
    """
    Print error messages.
    """
    if current_log_level() >= _LOG_LEVEL_ERROR:
        if args:
            fmt = fmt % args
        print(ticks_ms(), "ERROR", fmt)


def warning(fmt, *args):
    """
    Print warning messages.
    """
    if current_log_level() >= _LOG_LEVEL_WARNING:
        if args:
            fmt = fmt % args
        print(ticks_ms(), "WARN", fmt)


def info(fmt, *args):
    """
    Print info messages.
    """
    if current_log_level() >= _LOG_LEVEL_INFO:
        if args:
            fmt = fmt % args
        print(ticks_ms(), "INFO", fmt)


def debug(fmt, *args):
    """
    Print debug messages.
    """
    if current_log_level() >= _LOG_LEVEL_DEBUG:
        if args:
            fmt = fmt % args
        print(ticks_ms(), "DEBUG", fmt)

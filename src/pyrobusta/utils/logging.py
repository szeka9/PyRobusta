"""
Config-based logging module for different log levels
"""

from pyrobusta.utils.clock import ticks_ms

_LOG_LEVEL_OFF = -1  # Disable all logging
_LOG_LEVEL_ERROR = 0
_LOG_LEVEL_WARNING = 1
_LOG_LEVEL_INFO = 2
_LOG_LEVEL_DEBUG = 3

_LEVEL = _LOG_LEVEL_INFO


def set_log_level(level):
    """
    Set the verbosity of logging.
    Possible values: off, error, warning, info, debug
    """
    global _LEVEL  # pylint: disable=W0603

    if level == "off":
        _LEVEL = _LOG_LEVEL_OFF
    elif level == "error":
        _LEVEL = _LOG_LEVEL_ERROR
    elif level == "warning":
        _LEVEL = _LOG_LEVEL_WARNING
    elif level == "info":
        _LEVEL = _LOG_LEVEL_INFO
    elif level == "debug":
        _LEVEL = _LOG_LEVEL_DEBUG
    else:
        raise ValueError()


def _log(verbosity, label, fmt, *args):
    if _LEVEL >= verbosity:
        if args:
            fmt = fmt % args
        print(ticks_ms(), label, fmt)


def error(fmt, *args):
    """
    Print error messages.
    """
    _log(_LOG_LEVEL_ERROR, "ERROR", fmt, *args)


def warning(fmt, *args):
    """
    Print warning messages.
    """
    _log(_LOG_LEVEL_WARNING, "WARN", fmt, *args)


def info(fmt, *args):
    """
    Print info messages.
    """
    _log(_LOG_LEVEL_INFO, "INFO", fmt, *args)


def debug(fmt, *args):
    """
    Print debug messages.
    """
    _log(_LOG_LEVEL_DEBUG, "DEBUG", fmt, *args)

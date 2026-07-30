"""
Adapter for time module to provide time-related functions.
"""

# pylint: disable=E1101

import time


def ticks_ms():
    """
    Return the current time in milliseconds.
    """
    return time.ticks_ms()


def ticks_add(ticks, delta):
    """
    Add a delta to the given ticks.
    """
    return time.ticks_add(ticks, delta)


def ticks_diff(ticks1, ticks2):
    """
    Return the difference between two ticks.
    """
    return time.ticks_diff(ticks1, ticks2)

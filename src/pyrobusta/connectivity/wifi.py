"""
Helpers for setting up Wi-Fi in station mode
"""

from time import sleep

from network import WLAN, STA_IF

from ..utils.config import get_config, CONF_WIFI_SSID, CONF_WIFI_PASSWORD
from ..utils import logging


def initialize():
    """
    Initialize WLAN interface in station mode
    """
    ssid = get_config(CONF_WIFI_SSID)
    password = get_config(CONF_WIFI_PASSWORD)

    if not ssid or not password:
        logging.warning(__name__ + ": missing SSID/password")
        return False

    sta_if = WLAN(STA_IF)
    sta_if.active(True)
    if sta_if.isconnected():
        logging.info(__name__ + f": already connected IP={sta_if.ifconfig()[0]}")
        return True

    sta_if.connect(ssid, password)

    timeout = 30
    while timeout > 0:
        if sta_if.isconnected():
            ip = sta_if.ifconfig()[0]
            logging.info(__name__ + f": connected, IP={ip}")
            return True
        sleep(1)
        timeout -= 1

    logging.warning(__name__ + ": connection failed")
    return False


def get_address():
    """
    Get the address of the WLAN interface
    """
    sta_if = WLAN(STA_IF)
    if sta_if.isconnected():
        return sta_if.ifconfig()[0]
    return None

"""
Helpers for setting up Wi-Fi in station mode.
"""

from time import sleep

from network import WLAN, STA_IF

from pyrobusta.utils.config import get_config, CONF_WIFI_SSID, CONF_WIFI_PASSWORD
from pyrobusta.utils import logging


def initialize():
    """
    Initialize WLAN station interface.
    """
    ssid = get_config(CONF_WIFI_SSID)
    password = get_config(CONF_WIFI_PASSWORD)

    if not ssid or not password:
        logging.error("%s: missing SSID/password", __name__)
        return False

    sta_if = WLAN(STA_IF)
    sta_if.active(True)
    addr = sta_if.ifconfig()[0]
    if sta_if.isconnected():
        logging.info("%s: already connected ip=[%s]", __name__, addr)
        return True

    sta_if.connect(ssid, password)

    timeout = 30
    while timeout > 0:
        if sta_if.isconnected():
            logging.info("%s: connected, ip=[%s]", __name__, addr)
            return True
        sleep(1)
        timeout -= 1

    logging.error("%s: connection failed", __name__)
    return False


def get_address():
    """
    Get the IP address of the WLAN station.
    """
    sta_if = WLAN(STA_IF)
    if sta_if.isconnected():
        return sta_if.ifconfig()[0]
    return None

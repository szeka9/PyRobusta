"""
Helpers for setting up Wi-Fi in station mode
"""

from network import WLAN, STA_IF
from ..utils.config import get_config
from ..utils import logging


def initialize():
    """
    Initialize WLAN interface in station mode
    """
    ssid = get_config("wifi_ssid")
    password = get_config("wifi_password")
    if not ssid or not password:
        logging.warning(__name__ + ": missing SSID/password, skip initialization")
        return

    sta_if = WLAN(STA_IF)
    sta_if.active(True)
    nets = sta_if.scan()
    for net in nets:
        if net[0].decode() == get_config("wifi_ssid"):
            logging.info(__name__ + f": network {net[0]} found!")
            sta_if.connect(net[0], get_config("wifi_password"))
            logging.info(__name__ + f": connected, available at {sta_if.ifconfig()[0]}")
            break


def get_address():
    """
    Get the address of the WLAN interface
    """
    sta_if = WLAN(STA_IF)
    return sta_if.ifconfig()[0]

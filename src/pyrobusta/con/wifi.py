"""
Helpers for setting up Wi-Fi in station mode
"""

from network import WLAN, STA_IF
from ..utils.config import get_config


def initialize():
    """
    Initialize WLAN interface in station mode
    """
    sta_if = WLAN(STA_IF)
    sta_if.active(True)
    nets = sta_if.scan()
    for net in nets:
        if net[0].decode() == get_config("wifi_ssid"):
            print(f"Network {net[0]} found!")
            sta_if.connect(net[0], get_config("wifi_password"))
            print("WLAN connection succeeded!")
            break


def get_address():
    """
    Get the address of the WLAN interface
    """
    sta_if = WLAN(STA_IF)
    return sta_if.ifconfig()[0]

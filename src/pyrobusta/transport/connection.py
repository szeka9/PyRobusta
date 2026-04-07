"""
Base class for representing a socket, providing common methods
and member variables for the socket server to use.
"""

import asyncio
from time import ticks_ms

from ..utils import logging


class BaseConnection:
    """
    BaseConnection class, accepting a StreamReader and StreamWriter.
    """

    __slots__ = ("id", "connected", "last_event", "_reader", "_writer")


    def __init__(self, reader, writer):
        """
        Base class for connection handling.
        :param reader: async reader stream object
        :param writer: async writer stream object
        """
        client_info = writer.get_extra_info("peername")
        self.id = str(client_info[0]) + ":" + str(client_info[1])
        self.connected = True
        self.last_event = ticks_ms()
        self._reader = reader
        self._writer = writer

    async def __aenter__(self):
       return self

    async def __aexit__(self, exc_type, exc_value, traceback):
       await self.close()

    async def read(self, read_bytes, decoding="utf8", timeout_seconds=0):
        """
        [Base] Implements client read function
        :return tuple: read_error, data
        - read_error is set to true upon timeout or other exception
        - data holds bytes or decoded string read from the socket
        """
        if not self.connected:
            raise OSError(f"{self.id} already closed")

        logging.debug(__name__ + f": read from {self.id}")
        self.last_event = ticks_ms()
        if timeout_seconds:
            request = await asyncio.wait_for(
                self._reader.read(read_bytes), timeout_seconds
            )
        else:
            request = await self._reader.read(read_bytes)
        if decoding:
            request = request.decode(decoding)
        return request

    async def write(self, data):
        if not self.connected:
            raise OSError(f"{self.id} already closed")

        logging.debug(__name__ + f": write to {self.id}")
        self._writer.write(data)
        await self._writer.drain()
        self.last_event = ticks_ms()

    async def close(self):
        """
        Async socket close method
        """
        if not self.connected:
            return OSError(f"{self.id} already closed")

        self.connected = False
        logging.debug(__name__ + f": close connection: {self.id}")
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError as e:
            logging.warning(__name__ + f": error while closing {self.id}: {e}")

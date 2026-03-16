"""
Base class for representing a socket, providing common methods
and member variables for the socket server to use.
"""

import asyncio
from time import ticks_ms


class SocketBase:
    """
    SocketBase class.
    """

    __slots__ = ("id", "connected", "reader", "writer", "last_event")

    def __init__(self, reader, writer):
        """
        Base class for socket handling
        :param reader: async reader stream object
        :param writer: async writer stream object
        """
        client_info = writer.get_extra_info("peername")
        self.id = str(client_info[0]) + ":" + str(client_info[1])
        self.connected = True
        self.reader = reader
        self.writer = writer
        self.last_event = ticks_ms()

    async def read(self, read_bytes, decoding="utf8", timeout_seconds=0):
        """
        [Base] Implements client read function
        :return tuple: read_error, data
        - read_error is set to true upon timeout or other exception
        - data holds bytes or decoded string read from the socket
        """
        print(f"[SocketBase] read from {self.id}")
        self.last_event = ticks_ms()
        if timeout_seconds:
            request = await asyncio.wait_for(
                self.reader.read(read_bytes), timeout_seconds
            )
        else:
            request = await self.reader.read(read_bytes)
        if decoding:
            request = request.decode(decoding)
        return request

    async def close(self):
        """
        Async socket close method
        """
        print(f"[SocketBase] close connection: {self.id}")
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except OSError as e:
            print(f"[SocketBase] Error while closing {self.id}: {e}")
        self.connected = False

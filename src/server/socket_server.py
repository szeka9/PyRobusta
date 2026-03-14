"""
Socket server application
"""

from asyncio import sleep_ms, start_server # pylint: disable=E1101
import gc
from time import ticks_ms, ticks_diff

from bindings.socket_http import SocketHttp
from con import wifi
from utils.config import get_config


class SocketServer:
    """
    Socket server class, handling global config (timeout, port, max connections etc.),
    and managing active sockets.
    """

    __slots__ = ["_host", "_max_sockets", "_port", "_timeout", "http"]

    CON_ACCEPT_TIMEOUT_MS = 5000  # Timeout value for accepting new connection
    CON_ACCEPT_SLEEP_MS = (
        100  # Duration of sleep between attempts to accept new connection
    )
    MAX_SOCKETS = int(get_config("socket_max_con"))
    SOCKET_TIMEOUT_SEC = 30
    LISTEN_PORT = 8000
    ACTIVE_SOCKETS = []

    @staticmethod
    def drop_client(socket):
        """Remove socket from active list"""
        print(f"[SocketBase] {socket.id} dropped")
        if socket in SocketServer.ACTIVE_SOCKETS:
            socket_idx = SocketServer.ACTIVE_SOCKETS.index(socket)
            SocketServer.ACTIVE_SOCKETS.pop(socket_idx)
            gc.collect()

    def __init__(self):
        self._host = "0.0.0.0"
        self._max_sockets = max(1, SocketServer.MAX_SOCKETS)
        self._port = SocketServer.LISTEN_PORT
        self._timeout = SocketServer.SOCKET_TIMEOUT_SEC
        self.http = None

    async def can_handle_new_socket(self):
        """
        Decide if the new socket can be handled.
        Evict closed/inactive sockets if needed.
        :return is_acceptable: true/false
        """
        gc.collect()
        con_timestamp = ticks_ms()
        while (
            ticks_diff(ticks_ms(), con_timestamp) < SocketServer.CON_ACCEPT_TIMEOUT_MS
        ):
            if len(SocketServer.ACTIVE_SOCKETS) < self._max_sockets:
                return True
            # Attempt to evict inactive clients
            for socket in SocketServer.ACTIVE_SOCKETS:
                socket_inactive = int(ticks_diff(ticks_ms(), socket.last_event) * 0.001)
                if not socket.connected or socket_inactive > self._timeout:
                    print(
                        (
                            f"[SocketServer] evicted {socket.id} "
                            f"timeout:{self._timeout - socket_inactive}s"
                        )
                    )
                    await socket.close()
                    SocketServer.drop_client(socket)
                    return True
            await sleep_ms(SocketServer.CON_ACCEPT_SLEEP_MS)
        return False

    async def accept_http(self, reader, writer):
        """
        Handle incoming socket connection for HTTP.
        - creates SocketHttp object
        """
        if not await self.can_handle_new_socket():
            print("[SocketServer] cannot accept new client")
            writer.close()
            await writer.wait_closed()
            return

        new_client = SocketHttp(reader, writer)
        print(f"[SocketServer] new client: {new_client.id}")
        SocketServer.ACTIVE_SOCKETS.append(new_client)
        await new_client.run()

    async def run_server(self):
        """
        Start asyncio socket server on the specified port.
        """
        addr = wifi.get_address()
        print(f"[SocketServer] Start SocketServer on {addr}")
        try:
            gc.collect()
            SocketHttp.init_pools(self._max_sockets)
            self.http = start_server(
                self.accept_http, self._host, self._port, backlog=self._max_sockets
            )
            await self.http
            print(f"HTTP server ready, connect: http://{addr}")
        except MemoryError as e:
            print(f"Memory allocation failed: {e}")

    def __del__(self):
        print("[SocketServer] Terminated")
        if self.http:
            self.http.close()

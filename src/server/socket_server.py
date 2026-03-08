import asyncio
import gc
from time import ticks_ms, ticks_diff

from bindings.web_socket import WebSocket
from con import wifi
from utils.config import get_config

class SocketServer:
    """Socket server application"""
    __slots__ = ['_host', '_max_sockets', '_port', '_timeout', 'web']

    CON_ACCEPT_TIMEOUT_MS = 5000 # Timeout value for accepting new connection
    CON_ACCEPT_SLEEP_MS = 100    # Duration of sleep between attempts to accept new connection
    MAX_SOCKETS = int(get_config("max_con"))
    SOCKET_TIMEOUT_SEC = 5
    LISTEN_PORT = 8000
    ACTIVE_SOCKETS = []


    @staticmethod
    def drop_client(socket):
        """Remove socket from active list"""
        print(f"[SocketBase] {socket.id} dropped")
        if socket in SocketServer.ACTIVE_SOCKETS:
            socket_idx = SocketServer.ACTIVE_SOCKETS.index(socket)
            SocketServer.ACTIVE_SOCKETS.pop(socket_idx)


    def __init__(self):
        self._host = '0.0.0.0'
        self._max_sockets = max(1, SocketServer.MAX_SOCKETS)
        self._port = SocketServer.LISTEN_PORT
        self._timeout = SocketServer.SOCKET_TIMEOUT_SEC


    async def accept_client(self, new_socket):
        print(f"[SocketServer] new client: {new_socket.id}")
        con_timestamp = ticks_ms()
        while ticks_ms() - con_timestamp < SocketServer.CON_ACCEPT_TIMEOUT_MS:
            if len(SocketServer.ACTIVE_SOCKETS) < self._max_sockets:
                SocketServer.ACTIVE_SOCKETS.append(new_socket)
                return True
            # Attempt to evict inactive clients
            for socket in SocketServer.ACTIVE_SOCKETS:
                socket_inactive = int(ticks_diff(ticks_ms(), socket.last_event) * 0.001)
                if not socket.connected or socket_inactive > self._timeout:
                    print(f"[SocketServer] accept new {new_socket.id} - evicted {socket.id} timeout:{self._timeout - socket_inactive}s")
                    await socket.close()
                    SocketServer.drop_client(socket)
                    return True
            await asyncio.sleep_ms(SocketServer.CON_ACCEPT_SLEEP_MS)

        print(f"[SocketServer] cannot accept new client {new_socket.id}")
        await new_socket.close()
        SocketServer.drop_client(new_socket)
        del new_socket
        return False


    async def web_socket(self, reader, writer):
        """
        Handle incoming new async requests towards the server
        - creates WebSocket object with the new incoming connection
        """
        new_client = WebSocket(reader, writer)
        if not await self.accept_client(new_client):
            return
        await new_client.run_web()


    async def run_server(self):
        """ """
        addr = wifi.get_address()
        print(f"[SocketServer] Start SocketServer on {addr}")
        try:
            gc.collect()
            WebSocket.init_pools(self._max_sockets)
            self.web = asyncio.start_server(self.web_socket, self._host, self._port, backlog=self._max_sockets)
            await self.web
            print(f"Web server ready, connect: http://{addr}")
        except MemoryError as e:
            print(f"Memory allocation failed [{self.client_id}]: {e}")


    def __del__(self):
        print("[SocketServer] Terminated")
        if self.server:
            self.server.close()
        if self.web:
            self.web.close()

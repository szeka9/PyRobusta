"""
Socket server application
"""

from asyncio import sleep_ms, start_server, run  # pylint: disable=E1101
import gc
import ssl
from time import ticks_ms, ticks_diff

from ..protocol import http
from ..bindings.socket_http import SocketHttp
from ..utils.config import get_config
from ..utils import logging


class HttpServer:
    """
    Socket server class, handling global config (timeout, port, max connections etc.),
    and managing active sockets.
    """

    __slots__ = ["_host", "_max_sockets", "_port", "_timeout", "_server"]

    ACTIVE_SOCKETS = []
    CON_ACCEPT_TIMEOUT_MS = 5000  # Timeout value for accepting new connection
    CON_ACCEPT_SLEEP_MS = (
        100  # Duration of sleep between attempts to accept new connection
    )
    MAX_SOCKETS = int(get_config("socket_max_con"))
    SOCKET_TIMEOUT_SEC = 30
    LISTEN_PORT_HTTP = 8080
    LISTEN_PORT_HTTPS = 4443
    TLS_CERT_PATH = "cert.der"
    TLS_KEY_PATH = "key.der"

    @classmethod
    async def drop_client(cls, socket):
        """Remove socket from active list"""
        if socket not in cls.ACTIVE_SOCKETS:
            return
        logging.debug(f"[HttpServer] {socket.id} dropped")
        await socket.close()
        cls.ACTIVE_SOCKETS.remove(socket)
        del socket
        gc.collect()

    def __init__(self):
        self._host = "0.0.0.0"
        self._max_sockets = max(1, HttpServer.MAX_SOCKETS)
        self._port = (
            HttpServer.LISTEN_PORT_HTTPS
            if get_config("tls").lower() == "true"
            else HttpServer.LISTEN_PORT_HTTP
        )
        self._timeout = HttpServer.SOCKET_TIMEOUT_SEC
        self._server = None

    async def can_handle_new_socket(self):
        """
        Decide if the new socket can be handled.
        Evict closed/inactive sockets if needed.
        :return is_acceptable: true/false
        """
        gc.collect()
        con_timestamp = ticks_ms()
        while ticks_diff(ticks_ms(), con_timestamp) < self.CON_ACCEPT_TIMEOUT_MS:
            if len(self.ACTIVE_SOCKETS) < self._max_sockets:
                return True
            # Attempt to evict inactive clients
            for socket in self.ACTIVE_SOCKETS:
                socket_inactive = int(ticks_diff(ticks_ms(), socket.last_event) * 0.001)
                if not socket.connected or socket_inactive > self._timeout:
                    logging.debug(
                        (
                            f"[HttpSever] evicted {socket.id} "
                            f"timeout:{self._timeout - socket_inactive}s"
                        )
                    )
                    await self.drop_client(socket)
                    return True
            await sleep_ms(self.CON_ACCEPT_SLEEP_MS)
        return False

    async def accept_http(self, reader, writer):
        """
        Handle incoming socket connection for HTTP.
        - creates SocketHttp object
        """
        if not await self.can_handle_new_socket():
            logging.debug("[HttpSever] cannot accept new client")
            writer.close()
            await writer.wait_closed()
            return

        new_client = SocketHttp(reader, writer)
        logging.debug(f"[HttpSever] new client: {new_client.id}")
        self.ACTIVE_SOCKETS.append(new_client)
        await new_client.run()

    async def run_server(self):
        """
        Start asyncio socket server on the specified port.
        """
        try:
            gc.collect()
            http.enable_optional_features()
            logging.debug(f"Registered endpoints: {http.HttpEngine.ENDPOINTS}")
            SocketHttp.init_pools(self._max_sockets)
            ssl_ctx = None
            if get_config("tls").lower() == "true":
                ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_ctx.load_cert_chain(self.TLS_CERT_PATH, self.TLS_KEY_PATH)
            self._server = await start_server(
                self.accept_http,
                self._host,
                self._port,
                backlog=self._max_sockets,
                ssl=ssl_ctx,
            )
            logging.info("[HttpSever] Started")
        except MemoryError as e:
            logging.warning(f"[HttpSever] Memory allocation failed: {e}")

    async def terminate(self):
        """
        Terminate HTTP server and close sockets
        """
        logging.info("[HttpSever] Terminated")
        while self.ACTIVE_SOCKETS:
            await self.drop_client(self.ACTIVE_SOCKETS[0])
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        gc.collect()


def main():
    """
    Start socket server async task.
    """
    run(HttpServer().run_server())

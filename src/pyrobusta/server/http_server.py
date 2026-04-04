"""
Socket server application
"""

from gc import collect, mem_free
from asyncio import sleep_ms, start_server, run  # pylint: disable=E1101
from time import ticks_ms, ticks_diff

from ..protocol import http
from ..bindings.socket_http import SocketHttp
from ..stream.buffer import MemoryPool, SlidingBuffer
from ..utils.config import (
    get_config,
    CONF_HTTP_PORT,
    CONF_HTTPS_PORT,
    CONF_HTTP_MEM_CAP,
    CONF_TLS,
    CONF_SOCKET_MAX_CON,
)
from ..utils.helpers import normalize_path
from ..utils import logging


class HttpServer:
    """
    Socket server class, handling global config (timeout, port, max connections etc.),
    and managing active clients.
    """

    __slots__ = ["_host", "_port", "_server", "_max_clients"]

    ACTIVE_CLIENTS = []

    # ---------------
    # Server settings
    # ---------------
    CON_ACCEPT_TIMEOUT_MS = 5000  # Timeout value for accepting new connection
    CON_ACCEPT_SLEEP_MS = (
        100  # Duration of sleep between attempts to accept new connection
    )
    LISTEN_PORT_HTTP = get_config(CONF_HTTP_PORT)
    LISTEN_PORT_HTTPS = get_config(CONF_HTTPS_PORT)
    TLS_CERT_PATH = "/cert.der"
    TLS_KEY_PATH = "/key.der"
    CON_TIMEOUT_S = 30

    # -----------------------------------------
    # Constants for controlled memory footprint
    # -----------------------------------------

    MEM_CAP = get_config(CONF_HTTP_MEM_CAP)  # Default memory cap (percentage / 100)
    SEND_BUF_MIN_BYTES = 512  # Minimum buffer size for responses
    SEND_BUF_MAX_BYTES = 4096  # Max buffer size for responses
    RECV_BUF_MIN_BYTES = 512  # Minimum buffer size for requests
    RECV_BUF_MAX_BYTES = 4096  # Max buffer size for requests
    CON_OVERHEAD_BYTES = 1024  # Overhead per connection

    # ------------------------------------------
    # Buffer pools - initialized by init_pools()
    # ------------------------------------------

    RECV_POOL = None
    SEND_POOL = None

    @classmethod
    def _init_pools(cls, max_clients):
        """
        Initialize pool of buffers for sending/receiving based on different profiles
        """
        mem_available = mem_free()
        con_limit = max_clients
        usable = int(cls.MEM_CAP * mem_available)
        is_low_memory = (usable / con_limit) < (
            cls.RECV_BUF_MAX_BYTES + cls.SEND_BUF_MAX_BYTES + cls.CON_OVERHEAD_BYTES
        )
        if is_low_memory:
            logging.warning(
                __name__ + ".init_pools: low-memory mode with reduced buffer size"
            )
        recv_size = cls.RECV_BUF_MIN_BYTES if is_low_memory else cls.RECV_BUF_MAX_BYTES
        send_size = cls.SEND_BUF_MIN_BYTES if is_low_memory else cls.SEND_BUF_MAX_BYTES
        per_con = recv_size + send_size + cls.CON_OVERHEAD_BYTES
        if usable < per_con:
            raise MemoryError(
                (
                    f"Insufficient memory: {mem_available // 1024} KB "
                    f"at {cls.MEM_CAP*100}% cap, "
                    f"at least {per_con // 1024} KB required"
                )
            )
        con_limit = min(usable // per_con, con_limit)
        logging.info((__name__ + f".init_pools: {con_limit} connection(s) allowed"))
        cls.RECV_POOL = MemoryPool(recv_size, con_limit, wrapper=SlidingBuffer)
        cls.SEND_POOL = MemoryPool(send_size, con_limit, wrapper=SlidingBuffer)

    @classmethod
    async def _drop_client(cls, client):
        """Remove client from active list"""
        if client not in cls.ACTIVE_CLIENTS:
            return
        logging.debug(__name__ + f": {client.id} dropped")
        await client.close()
        cls.ACTIVE_CLIENTS.remove(client)
        del client
        collect()

    # ----------------
    # Instance methods
    # ----------------

    def __init__(self):
        self._host = "0.0.0.0"
        self._port = (
            HttpServer.LISTEN_PORT_HTTPS
            if get_config(CONF_TLS)
            else HttpServer.LISTEN_PORT_HTTP
        )
        self._server = None
        self._max_clients = 0

    async def can_handle_new_client(self):
        """
        Decide if the new socket can be handled.
        Evict closed/inactive sockets if needed.
        :return is_acceptable: true/false
        """
        collect()
        con_timestamp = ticks_ms()
        while ticks_diff(ticks_ms(), con_timestamp) < self.CON_ACCEPT_TIMEOUT_MS:
            if len(self.ACTIVE_CLIENTS) < self._max_clients:
                return True
            # Attempt to evict inactive clients
            for client in self.ACTIVE_CLIENTS:
                client_inactive = int(ticks_diff(ticks_ms(), client.last_event) * 0.001)
                if not client.connected or client_inactive > self.CON_TIMEOUT_S:
                    logging.debug(
                        (
                            __name__ + f": evicted {client.id} "
                            f"timeout: {self.CON_TIMEOUT_S - client_inactive}s"
                        )
                    )
                    await self._drop_client(client)
            await sleep_ms(self.CON_ACCEPT_SLEEP_MS)
        return False

    async def _reserve_buffers(self):
        if self.SEND_POOL is None or self.RECV_POOL is None:
            raise RuntimeError("Pools are uninitialized")

        recv_buf = None
        send_buf = None

        while not recv_buf or not send_buf:
            if not recv_buf:
                recv_buf = self.RECV_POOL.reserve()
            if not send_buf:
                send_buf = self.SEND_POOL.reserve()
            await sleep_ms(self.CON_ACCEPT_SLEEP_MS)

        return recv_buf, send_buf

    async def _accept_socket(self, reader, writer):
        """
        Handle incoming socket connection for HTTP.
        - creates SocketHttp object
        """
        if not await self.can_handle_new_client():
            logging.debug(__name__ + ": cannot accept new client")
            writer.close()
            await writer.wait_closed()
            return

        try:
            recv_buf, send_buf = await self._reserve_buffers()
            new_client = SocketHttp(reader, writer, recv_buf, send_buf)
            logging.debug(__name__ + f": accept {new_client.id}")
            self.ACTIVE_CLIENTS.append(new_client)
            await new_client.run()
        except Exception as e:  # pylint: disable=W0718
            logging.warning(__name__ + f": error in run(): {e}")
        finally:
            if send_buf:
                send_buf.consume()
                self.SEND_POOL.release(send_buf)
            if recv_buf:
                recv_buf.consume()
                self.RECV_POOL.release(recv_buf)
            collect()

    async def start_socket_server(self):
        """
        Start asyncio socket server on the specified port.
        """
        try:
            collect()
            http.enable_optional_features()
            logging.debug(
                __name__ + f"registered endpoints: {http.HttpEngine.ENDPOINTS}"
            )
            self._max_clients = get_config(CONF_SOCKET_MAX_CON)
            self._init_pools(self._max_clients)
            ssl_ctx = None

            if get_config(CONF_TLS):
                import ssl

                ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_ctx.load_cert_chain(
                    normalize_path(self.TLS_CERT_PATH),
                    normalize_path(self.TLS_KEY_PATH),
                )

            self._server = await start_server(
                self._accept_socket,
                self._host,
                self._port,
                backlog=max(1, self._max_clients),
                ssl=ssl_ctx,
            )
            logging.info(__name__ + ": started")
        except MemoryError as e:
            logging.warning(__name__ + f": allocation failed - {e}")

    async def terminate(self):
        """
        Terminate HTTP server and drop clients
        """
        logging.info(__name__ + ": terminated")
        while self.ACTIVE_CLIENTS:
            await self._drop_client(self.ACTIVE_CLIENTS[0])
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        collect()


def main():
    """
    Start HTTP server async task.
    """
    run(HttpServer().start_socket_server())

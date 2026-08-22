"""
Socket server application
"""

from gc import collect, mem_free, mem_alloc
from asyncio import sleep_ms, start_server  # pylint: disable=E1101
from time import ticks_ms, ticks_diff

from pyrobusta.protocol.http import HttpEngine
from pyrobusta.bindings.http_connection import HttpConnection
from pyrobusta.stream.buffer import MemoryPool, SlidingBuffer
from pyrobusta.utils.logging import error, warning, info, debug


class HttpServer:
    """
    Socket server class, handling global config (timeout, port, max connections etc.),
    and managing active clients.
    """

    __slots__ = ["_server"]

    ACTIVE_CLIENTS = []

    # ---------------
    # Server settings
    # ---------------

    CON_ACCEPT_TIMEOUT_MS = 5000  # Timeout value for accepting new connection
    CON_ACCEPT_SLEEP_MS = (
        100  # Duration of sleep between attempts to accept new connection
    )

    # -----------------------------------------
    # Constants for controlled memory footprint
    # -----------------------------------------

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
    def _init_pools(cls, max_clients, mem_cap):
        """
        Initialize pool of buffers for sending/receiving based on different profiles.
        :param max_clients: maximum number of HTTP clients
        :param mem_cap: fraction of heap reserved for stream buffers
        """
        mem_available = mem_free() + mem_alloc()
        con_limit = max_clients
        usable = int(mem_cap * mem_available)
        is_low_memory = (usable / con_limit) < (
            cls.RECV_BUF_MAX_BYTES + cls.SEND_BUF_MAX_BYTES + cls.CON_OVERHEAD_BYTES
        )
        if is_low_memory:
            warning("%s: low-memory mode with reduced buffer size", __name__)
        recv_size = cls.RECV_BUF_MIN_BYTES if is_low_memory else cls.RECV_BUF_MAX_BYTES
        send_size = cls.SEND_BUF_MIN_BYTES if is_low_memory else cls.SEND_BUF_MAX_BYTES
        per_con = recv_size + send_size + cls.CON_OVERHEAD_BYTES
        if usable < per_con:
            raise MemoryError(
                (
                    f"Insufficient memory: {mem_available // 1024} KB "
                    f"at {mem_cap*100}% cap, "
                    f"at least {per_con // 1024} KB required"
                )
            )
        con_limit = min(usable // per_con, con_limit)
        info("%s: %s connection(s) allowed", __name__, con_limit)
        cls.RECV_POOL = MemoryPool(recv_size, con_limit, wrapper=SlidingBuffer)
        cls.SEND_POOL = MemoryPool(send_size, con_limit, wrapper=SlidingBuffer)

    # ----------------
    # Instance methods
    # ----------------

    def __init__(self):
        self._server = None

    async def _reserve_buffers(self):
        """
        Reserve and return request and response buffers.
        """
        if self.SEND_POOL is None or self.RECV_POOL is None:
            raise RuntimeError("Pools are uninitialized")

        recv_buf = None
        send_buf = None
        deadline = ticks_ms() + self.CON_ACCEPT_TIMEOUT_MS

        while (not recv_buf or not send_buf) and ticks_diff(ticks_ms(), deadline) < 0:
            if not recv_buf:
                recv_buf = self.RECV_POOL.reserve()
            if not send_buf:
                send_buf = self.SEND_POOL.reserve()
            await sleep_ms(self.CON_ACCEPT_SLEEP_MS)

        return recv_buf, send_buf

    async def _accept_socket(self, reader, writer):
        """
        Handle incoming socket connection for HTTP.
        - creates HttpConnection object
        :param reader: asyncio StreamReader
        :param reader: asyncio StreamWriter
        """
        client = None
        try:
            recv_buf, send_buf = await self._reserve_buffers()

            if recv_buf is None or send_buf is None:
                debug(
                    "%s: connection from %s rejected (server at capacity)",
                    __name__,
                    writer.get_extra_info("peername")[0],
                )
                writer.close()
                await writer.wait_closed()
                return

            client = HttpConnection(reader, writer, recv_buf, send_buf)
            debug("%s: accept client=[%s]", __name__, client.id)
            self.ACTIVE_CLIENTS.append(client)
            async with client:
                await client.run()
        except Exception as e:  # pylint: disable=W0718
            warning(
                "%s: client=[%s] error=[%s]",
                __name__,
                writer.get_extra_info("peername")[0],
                e,
            )
        finally:
            if send_buf:
                send_buf.consume()
                self.SEND_POOL.release(send_buf)
            if recv_buf:
                recv_buf.consume()
                self.RECV_POOL.release(recv_buf)
            if client and client in self.ACTIVE_CLIENTS:
                self.ACTIVE_CLIENTS.remove(client)
            collect()

    async def start_socket_server(self, host, port, max_clients, mem_cap, ssl_ctx=None):
        """
        Start asyncio socket server on the specified port.
        """
        if self._server is not None:
            raise RuntimeError("Socket server already started")

        try:
            collect()
            debug("%s: registered routes: %s", __name__, HttpEngine.ROUTES)
            self._init_pools(max_clients, mem_cap)
            self._server = await start_server(
                self._accept_socket,
                host,
                port,
                backlog=max(1, max_clients),
                ssl=ssl_ctx,
            )
            info("%s: started", __name__)
        except MemoryError as e:
            error("%s: allocation error=[%s]", __name__, e)

    async def terminate(self):
        """
        Terminate HTTP server and drop clients.
        """
        info("%s: terminated", __name__)
        while self.ACTIVE_CLIENTS:
            client = self.ACTIVE_CLIENTS[0]
            debug("%s: client=[%s] dropped", __name__, client.id)
            self.ACTIVE_CLIENTS.remove(client)
            await client.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        collect()

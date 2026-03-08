import asyncio
from gc import mem_free, collect

from stream.buffer import MemoryPool, SlidingBuffer, BufferFullError
from transport.socket import SocketBase
from protocol.web import WebEngine
from utils.config import get_config

class WebSocket(SocketBase):
    # Constants for memory footprint
    MEM_CAP  = float(get_config("mem_cap"))    # Default memory cap (percentage / 100) of free heap
    SEND_BUF_MIN_BYTES = 512                    # Minimum buffer size for responses
    SEND_BUF_MAX_BYTES = 4096                   # Max buffer size for responses
    RECV_BUF_MIN_BYTES = 2048                   # Minimum buffer size for requests
    RECV_BUF_MAX_BYTES = 4096                   # Max buffer size for requests
    CONN_OVERHEAD = 1024                        # Overhead per connection
    MTU_SIZE = 1460                             # TCP maximum transmission unit

    # Timing settings
    STATE_MACHINE_SLEEP_MS = 2
    RESP_HANDLER_SLEEP_MS = 2
    RECV_TIMEOUT_SECONDS = 10

    # Static buffer pools - initialized by init_pools()
    RECV_POOL = None
    SEND_POOL = None

    @staticmethod
    def init_pools(max_sockets):
        """
        Initialize pool of buffers for sending/receiving based on different profiles
        """
        mem_available = mem_free()
        con_limit = max(1, max_sockets)
        usable = int(WebSocket.MEM_CAP * mem_available)
        is_low_memory = (usable / con_limit) < \
            (WebSocket.RECV_BUF_MAX_BYTES + WebSocket.SEND_BUF_MAX_BYTES + WebSocket.CONN_OVERHEAD)
        if is_low_memory:
            print((
                "[INFO] WebSocket.init_pools: low-memory mode with reduced buffer size, "
                "decrease max_clients to use larger buffers"
            ))
        recv_size = WebSocket.RECV_BUF_MIN_BYTES if is_low_memory else WebSocket.RECV_BUF_MAX_BYTES
        send_size = WebSocket.SEND_BUF_MIN_BYTES if is_low_memory else WebSocket.SEND_BUF_MAX_BYTES
        per_conn = recv_size + send_size + WebSocket.CONN_OVERHEAD
        if usable < per_conn:
            raise MemoryError((
                f"Insufficient memory for webserver: {mem_available // 1024} KB, "
                f"at least {per_conn // 1024} KB required"
            ))
        con_limit = min(
            usable // per_conn,
            con_limit
        )
        print((
            f"[INFO] WebSocket.init_pools: {con_limit} connection(s) allowed"
        ))
        WebSocket.RECV_POOL = MemoryPool(recv_size, con_limit, wrapper=SlidingBuffer)
        WebSocket.SEND_POOL = MemoryPool(send_size, con_limit, wrapper=SlidingBuffer)

    __slots__ = (
        "_engine",
        "_prev_state",
        "_recv_buf",
        "_send_buf"
    )

    def __init__(self, reader, writer):
        super().__init__(reader, writer)
        self._engine = WebEngine()
        self._prev_state = None
        self._recv_buf = None
        self._send_buf = None

    async def _flush_response(self):
        data = self._send_buf.peek()
        for i in range(0,len(data),WebSocket.MTU_SIZE):
            self.writer.write(data[i:i+WebSocket.MTU_SIZE])
            await self.writer.drain()
        self._send_buf.consume()

    async def run_web(self):
        await self._reserve_buffers()
        self._prev_state = None
        try:
            while self._engine.state is not None:
                await self._run_state_machine()
                await asyncio.sleep_ms(WebSocket.STATE_MACHINE_SLEEP_MS)
        except Exception as e:
            print(f"[WebSocket] error in run_web: {e}")
        finally:
            if self._send_buf:
                self._send_buf.consume()
                WebSocket.SEND_POOL.release(self._send_buf)
            if self._recv_buf:
                self._recv_buf.consume()
                WebSocket.RECV_POOL.release(self._recv_buf)
            await self.close()
            collect()

    async def _reserve_buffers(self):
        if WebSocket.SEND_POOL is None or WebSocket.RECV_POOL is None:
            raise RuntimeError("Buffer pools are uninitialized")

        while not self._recv_buf or not self._send_buf:
            if not self._recv_buf:
                self._recv_buf = WebSocket.RECV_POOL.reserve()
            if not self._send_buf:
                self._send_buf = WebSocket.SEND_POOL.reserve()
            await asyncio.sleep_ms(WebSocket.STATE_MACHINE_SLEEP_MS)

    async def _run_state_machine(self):
        if self._prev_state == self._engine.state or self._prev_state is None:
            num_read = await self._read_to_buf()
            if not num_read:
                return
        try:
            resp_handler = None
            while self._engine.state is not None:
                self._prev_state = self._engine.state
                resp_handler = self._engine.state(self._recv_buf, self._send_buf)
                if not self._send_buf.size():
                    break
                await self._flush_response()
                await asyncio.sleep_ms(WebSocket.STATE_MACHINE_SLEEP_MS)
        except BufferFullError:
            self._engine.on_failure(self._send_buf, b'Buffer full')
            await self._flush_response()
            return
        except Exception as e:
            print(f"[WebSocket] error in _run_state_machine: {e}")
            self._engine.on_failure(self._send_buf, str(e).encode("ascii"))
            await self._flush_response()
            return
        if self._engine.state is None and resp_handler is not None:
            await self._response_handler(resp_handler)

    async def _read_to_buf(self):
        buf_free = self._recv_buf.capacity - self._recv_buf.size()
        if not buf_free:
            self._engine.on_buffer_full(self._send_buf)
            await self._flush_response()
            return 0
        try:
            request = await self.read(read_bytes=buf_free,
                                      decoding=None,
                                      timeout_seconds=WebSocket.RECV_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self._engine.on_timeout(self._send_buf)
            await self._flush_response()
            return 0
        except Exception as e:
            self._engine.on_failure(self._send_buf, b"Read error" + e.encode("ascii"))
            await self._flush_response()
            return 0
        self._recv_buf.write(request)
        return len(request)

    async def _response_handler(self, resp_handler):
        if "closure" == type(resp_handler).__name__:
            for is_finished in resp_handler(self._send_buf):
                await self._flush_response()
                if is_finished:
                    break
                await asyncio.sleep_ms(WebSocket.RESP_HANDLER_SLEEP_MS)
        elif type(resp_handler).__name__ in ("FileIO", "BytesIO"):
            with resp_handler as rh:
                while True:
                    view = self._send_buf.writable_view()
                    num_read = rh.readinto(view)
                    if not num_read:
                        break
                    self._send_buf.commit(num_read)
                    await self._flush_response()
                    await asyncio.sleep_ms(WebSocket.RESP_HANDLER_SLEEP_MS)
        else:
            self._engine.on_failure(self._send_buf, f"Invalid response handler {type(resp_handler).__name__}".encode("ascii"))
            await self._flush_response()


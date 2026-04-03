"""
HTTP application-layer interface for socket connections.
"""

import asyncio
from asyncio import sleep_ms  # pylint: disable=E1101
from gc import collect

from ..stream.buffer import BufferFullError
from ..transport.socket import SocketBase
from ..protocol.http import HttpEngine, ServerBusyError, HeaderParsingError
from ..utils import logging


class SocketHttp(SocketBase):
    """
    HTTP wrapper class for representing HTTP socket connections, with
    buffer management and state machine parser.
    """

    MTU_SIZE = 1460
    STATE_MACHINE_SLEEP_MS = 2
    RESP_HANDLER_SLEEP_MS = 2
    RECV_TIMEOUT_SECONDS = 10

    __slots__ = ("_engine", "_prev_state", "_recv_buf", "_send_buf")

    def __init__(self, reader, writer, recv_buf, send_buf):
        super().__init__(reader, writer)
        self._engine = HttpEngine()
        self._prev_state = None
        self._recv_buf = recv_buf
        self._send_buf = send_buf

    async def _flush_response(self):
        data = self._send_buf.peek()
        for i in range(0, len(data), SocketHttp.MTU_SIZE):
            self.writer.write(data[i : i + SocketHttp.MTU_SIZE])
            await self.writer.drain()
        self._send_buf.consume()

    async def run(self):
        """
        Handle socket connection with HTTP state machine parser.
        """
        self._prev_state = None
        try:
            while self._engine.state is not None:
                await self._run_state_machine()
                await sleep_ms(SocketHttp.STATE_MACHINE_SLEEP_MS)
        finally:
            await self.close()
            collect()

    async def _read_to_buf(self):
        buf_free = self._recv_buf.capacity - self._recv_buf.size()
        if not buf_free:
            self._engine.on_buffer_full(self._send_buf)
            await self._flush_response()
            return 0
        try:
            request = await self.read(
                read_bytes=buf_free,
                decoding=None,
                timeout_seconds=SocketHttp.RECV_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._engine.on_timeout(self._send_buf)
            await self._flush_response()
            return 0
        except Exception as e:  # pylint: disable=W0718
            self._engine.on_failure(
                self._send_buf, b"Read error: " + str(e).encode("ascii")
            )
            await self._flush_response()
            return 0
        self._recv_buf.write(request)
        logging.debug(__name__ + f"._read_to_buf: [{request}]")
        return len(request)

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
                await sleep_ms(SocketHttp.STATE_MACHINE_SLEEP_MS)
        except BufferFullError:
            self._engine.on_failure(self._send_buf, b"Buffer full")
            await self._flush_response()
            return
        except ServerBusyError:
            self._engine.on_unavailable(self._send_buf)
            await self._flush_response()
            return
        except HeaderParsingError:
            self._engine.on_client_error(self._send_buf, b"Invalid headers")
            await self._flush_response()
            return
        except Exception as e:  # pylint: disable=W0718
            logging.warning(__name__ + f"._run_state_machine: {e}")
            self._engine.on_failure(self._send_buf, str(e).encode("ascii"))
            await self._flush_response()
            return
        if self._engine.state is None and resp_handler is not None:
            await self._response_handler(resp_handler)

    async def _response_handler(self, resp_handler):
        if "closure" == type(resp_handler).__name__:
            for is_finished in resp_handler(self._send_buf):
                await self._flush_response()
                if is_finished:
                    break
                await sleep_ms(SocketHttp.RESP_HANDLER_SLEEP_MS)
        elif type(resp_handler).__name__ in ("FileIO", "BytesIO"):
            with resp_handler as rh:
                while True:
                    view = self._send_buf.writable_view()
                    num_read = rh.readinto(view)
                    if not num_read:
                        break
                    self._send_buf.commit(num_read)
                    await self._flush_response()
                    await sleep_ms(SocketHttp.RESP_HANDLER_SLEEP_MS)
        else:
            self._engine.on_failure(
                self._send_buf,
                f"Invalid response handler {type(resp_handler).__name__}".encode(
                    "ascii"
                ),
            )
            await self._flush_response()

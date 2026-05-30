"""
HTTP application-layer interface for socket connections.
"""

import asyncio
from asyncio import sleep_ms  # pylint: disable=E1101

from ..stream.buffer import BufferFullError
from ..transport.connection import BaseConnection
from ..protocol.http import HttpEngine
from ..utils import logging


class HttpConnection(BaseConnection):
    """
    HTTP wrapper class for representing HTTP socket connections, with
    buffer management and state machine parser.
    """

    MTU_SIZE = 1460
    STATE_MACHINE_SLEEP_MS = 2
    RECV_TIMEOUT_SECONDS = 10

    __slots__ = ("_engine", "_prev_state", "_recv_buf", "_send_buf")

    def __init__(self, reader, writer, recv_buf, send_buf):
        super().__init__(reader, writer)
        self._engine = HttpEngine()
        self._prev_state = None
        self._recv_buf = recv_buf
        self._send_buf = send_buf

    async def run(self):
        """
        Handle socket connection with HTTP state machine parser.
        """
        self._prev_state = None
        while not self._engine.is_terminated():
            await self._run_state_machine()
            await sleep_ms(self.STATE_MACHINE_SLEEP_MS)
            if self._engine.is_terminated() and self._engine.do_keep_alive():
                self._engine.reset()
                self._prev_state = None

    async def _flush_response(self):
        data = self._send_buf.peek()
        for i in range(0, len(data), self.MTU_SIZE):
            await self.write(data[i : i + self.MTU_SIZE])
        self._send_buf.consume()

    async def _read_to_buf(self):
        buf_free = self._recv_buf.capacity - self._recv_buf.size()
        if not buf_free:
            raise BufferFullError()
        request = await self.read(
            read_bytes=buf_free,
            decoding=None,
            timeout_seconds=self.RECV_TIMEOUT_SECONDS,
        )
        self._recv_buf.write(request)
        logging.debug(__name__ + f"._read_to_buf: [{request}]")
        return len(request)

    async def _run_state_machine(self):
        # [1] read request
        if self._prev_state == self._engine.state or (
            self._prev_state is None and not self._recv_buf.size()
        ):
            try:
                num_read = await self._read_to_buf()
                if not num_read:
                    self._engine.abort(400)
                    self._engine.set_response_body(b"Incomplete request")
            except BufferFullError:
                self._engine.abort(413)
            except asyncio.TimeoutError:
                self._engine.abort(408)
            except Exception as e:  # pylint: disable=W0718
                self._engine.abort(500)
                self._engine.set_response_body(b"Read error: " + str(e).encode("ascii"))

        # [2] process request by state machine
        for _ in self._engine.run(self._recv_buf):
            if self._prev_state == self._engine.state:
                # No state transition occurred, read more data
                break
            self._prev_state = self._engine.state
            await sleep_ms(self.STATE_MACHINE_SLEEP_MS)

        # [3] write response
        if not self._engine.is_request_empty() and self._engine.is_terminated():
            self._engine.write_response_head(self._send_buf)
            await self._flush_response()
            if self._engine.resp_handler is not None:
                await self._response_handler(self._engine.resp_handler)

    async def _response_handler(self, resp_handler):
        if "closure" == type(resp_handler).__name__:
            if self._engine.get_response_header(b"transfer-encoding") == b"chunked":
                for is_finished in resp_handler(self._send_buf):
                    await self.write(b"%x\r\n" % self._send_buf.size())
                    await self._flush_response()
                    await self.write(b"\r\n")
                    if is_finished:
                        await self.write(b"0\r\n\r\n")
                        break
                    await sleep_ms(self.STATE_MACHINE_SLEEP_MS)
            else:
                for is_finished in resp_handler(self._send_buf):
                    await self._flush_response()
                    if is_finished:
                        break
                    await sleep_ms(self.STATE_MACHINE_SLEEP_MS)
        elif type(resp_handler).__name__ in ("FileIO", "BytesIO"):
            try:
                while True:
                    view = self._send_buf.writable_view()
                    num_read = resp_handler.readinto(view)
                    if not num_read:
                        break
                    self._send_buf.commit(num_read)
                    await self._flush_response()
                    await sleep_ms(self.STATE_MACHINE_SLEEP_MS)
            finally:
                resp_handler.close()
        else:
            raise RuntimeError(
                f"Invalid response handler {type(resp_handler).__name__}"
            )

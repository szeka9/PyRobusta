"""
Data structures for buffered processing & streaming
"""

import gc


class BufferOverflowError(ValueError):
    """Raised when writing more data than the buffer can hold."""

    pass


class BufferUnderflowError(ValueError):
    """Raised when consuming more data than the buffer currently contains."""

    pass


class MemoryPool:
    """
    Preallocated bytearray-backed memory pool that returns reusable memoryview slices
    for coroutine-based streaming without additional heap allocation.
    """

    __slots__ = ("_pool", "free")

    def __init__(self, block_size, block_count, wrapper=None):
        """
        Initialize memory pool.
        :param block_size: size of each memory block in bytes
        :param block_count: number of reservable memory blocks
        :param wrapper: wrapper class (abstraction layer) to access the memory, e.g. SlidingBuffer
        """
        self._pool = bytearray(block_size * block_count)
        self.free = []

        for i in range(block_count):
            self.free.append(
                memoryview(self._pool)[i * block_size : (i + 1) * block_size]
                if wrapper is None
                else wrapper(
                    memoryview(self._pool)[i * block_size : (i + 1) * block_size]
                )
            )
            gc.collect()

    def reserve(self):
        """
        Returns free memory block if there is any.
        :return block: set to None if there is no free block
        """
        if self.free:
            return self.free.pop()
        return None

    def release(self, block):
        """
        Reintroduce already reserved block in the shared pool.
        """
        self.free.append(block)


class SlidingBuffer:
    """
    A linear sliding-window buffer over a fixed-size bytearray or its memoryview.

    'start' and 'end' indices are maintained, such that
    the readable region is always buffer[start:end], and the writeable
    region is buffer[end:capacity], with the following invariant:
    0 <= start <= end <= capacity

    Key features:
    - Zero-copy access via memoryview slices for both readable and writable regions
    - Incremental consumption by advancing 'start'
    - Incremental writes by advancing 'end'
    - Automatic in-place compaction when additional space is
      required and unused bytes exist before 'start'
    - Bounded memory usage; no dynamic reallocation
    """

    __slots__ = ("_start", "_end", "_mv", "capacity")

    def __init__(self, buffer: memoryview):
        self._start = 0
        self._end = 0
        self._mv = buffer
        self.capacity = len(buffer)

    def size(self) -> int:
        """
        Determine the window size.
        """
        return self._end - self._start

    def writable(self) -> int:
        """
        Determine the writeable size of the buffer.
        """
        return self.capacity - self._end

    def readable_view(self) -> memoryview:
        """
        Return a memoryview to the readable region of the buffer (window).
        """
        return self._mv[self._start : self._end]

    def writable_view(self) -> memoryview:
        """
        Return a memoryview to the writeable region of the buffer.
        """
        return self._mv[self._end : self.capacity]

    def _compact(self):
        """
        Compact the buffer by shifting the active
        window to the beginning of the bytearray.
        """
        if self._start == 0:
            return
        n = self._end - self._start
        for i in range(n):
            self._mv[i] = self._mv[self._start + i]
        self._start = 0
        self._end = n

    def peek(self, n=None) -> memoryview:
        """
        Return the first n bytes from the window,
        return the entire window when n is undefined.
        """
        if n is None:
            n = self.size()
        if n > self.size() or n < 0:
            raise IndexError()
        return self._mv[self._start : self._start + n]

    def write(self, data: bytes):
        """
        Write new data into the writable region and advance the 'end' index.
        """
        if len(data) > self.capacity:
            raise BufferOverflowError()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError()
        needed = len(data)
        if needed > self.capacity - self._end:
            self._compact()
            if needed > self.capacity - self._end:
                raise BufferOverflowError()
        for i in range(needed):
            self._mv[self._end + i] = data[i]
        self._end += needed

    def consume(self, n: int = None):
        """
        Discard the first n bytes of the window by advancing the 'start' index.
        """
        if n is None:
            n = self.size()
        if n > self.size():
            raise BufferUnderflowError()
        self._start += n
        if self._start == self._end:
            self._start = 0
            self._end = 0

    def prepare(self, n: int):
        """
        Check if the writeable region is larger or equal to n,
        otherwise attempt to compact the buffer.
        """
        if n > self.capacity:
            raise BufferOverflowError()

        if n > self.writable():
            self._compact()
            if n > self.writable():
                raise BufferOverflowError()

    def commit(self, n):
        """
        Increase the window size by n bytes by incrementing the 'end' index.
        """
        if self._end + n > self.capacity:
            raise BufferOverflowError()
        self._end += n

    def find(self, term: bytes) -> int:
        """
        Find and return the index of a search term in the current window.
        """
        for i in range(self._start, self._end - len(term) + 1):
            if self._mv[i : i + len(term)] == term:
                return i - self._start
        return -1

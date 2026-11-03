"""Bounded cursor over untrusted big-endian bytecode."""
from __future__ import annotations
import struct
from .errors import LoadError


class Reader:
    __slots__ = ("data", "pos", "error_code")

    def __init__(self, data: bytes, error_code: str = "LOAD_BAD_BYTECODE"):
        self.data = data
        self.pos = 0
        self.error_code = error_code

    def need(self, size: int) -> None:
        if size < 0 or size > len(self.data) - self.pos:
            raise LoadError(self.error_code, "bytecode is truncated: wanted " + str(size) + " byte(s) at offset " + str(self.pos) + ", file has " + str(len(self.data)))

    def bytes(self, size: int) -> bytes:
        self.need(size)
        start = self.pos
        self.pos += size
        return self.data[start:self.pos]

    def u8(self) -> int:
        self.need(1)
        value = self.data[self.pos]
        self.pos += 1
        return value

    def u16(self) -> int:
        return struct.unpack(">H", self.bytes(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.bytes(4))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.bytes(4))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self.bytes(8))[0]

    def f64(self) -> float:
        return struct.unpack(">d", self.bytes(8))[0]

    def done(self) -> bool:
        return self.pos == len(self.data)

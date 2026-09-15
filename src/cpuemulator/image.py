import struct
from dataclasses import dataclass, field
from pathlib import Path

from cpuemulator.arch import PROGRAM_BASE

MAGIC = b"A7X\0"
VERSION = 1
HEADER = struct.Struct("<4sHHHHHI")


class ImageError(ValueError):
    pass


@dataclass(slots=True)
class Image:
    entry: int = PROGRAM_BASE
    segments: list[tuple[int, bytes]] = field(default_factory=list)
    symbols: dict[str, int] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    lines: dict[int, tuple[int, int]] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return sum(len(data) for _, data in self.segments)

    def source(self, address: int) -> tuple[str, int] | None:
        location = self.lines.get(address)
        if location is None:
            return None
        return self.files[location[0]], location[1]

    def to_bytes(self) -> bytes:
        out = bytearray(
            HEADER.pack(
                MAGIC,
                VERSION,
                self.entry,
                len(self.segments),
                len(self.symbols),
                len(self.files),
                len(self.lines),
            )
        )
        for address, data in self.segments:
            out += struct.pack("<HH", address, len(data) & 0xFFFF)
            out += data
        for name, value in self.symbols.items():
            encoded = name.encode()
            out += struct.pack("<HB", value & 0xFFFF, len(encoded))
            out += encoded
        for path in self.files:
            encoded = path.encode()
            out += struct.pack("<H", len(encoded))
            out += encoded
        for address, (file, line) in sorted(self.lines.items()):
            out += struct.pack("<HHI", address, file, line)
        return bytes(out)

    @classmethod
    def from_bytes(cls, data: bytes) -> "Image":
        if len(data) < HEADER.size:
            raise ImageError("file is too short to be an A7X image")
        magic, version, entry, nsegments, nsymbols, nfiles, nlines = HEADER.unpack_from(data)
        if magic != MAGIC:
            raise ImageError("not an A7X image")
        if version != VERSION:
            raise ImageError(f"unsupported A7X version {version}")
        image = cls(entry)
        offset = HEADER.size
        try:
            for _ in range(nsegments):
                address, length = struct.unpack_from("<HH", data, offset)
                length = length or 0x10000
                offset += 4
                chunk = data[offset : offset + length]
                if len(chunk) != length:
                    raise ImageError(f"segment at {address:04X} is truncated")
                image.segments.append((address, chunk))
                offset += length
            for _ in range(nsymbols):
                value, length = struct.unpack_from("<HB", data, offset)
                offset += 3
                image.symbols[data[offset : offset + length].decode()] = value
                offset += length
            for _ in range(nfiles):
                (length,) = struct.unpack_from("<H", data, offset)
                offset += 2
                image.files.append(data[offset : offset + length].decode())
                offset += length
            for _ in range(nlines):
                address, file, line = struct.unpack_from("<HHI", data, offset)
                image.lines[address] = (file, line)
                offset += 8
        except (struct.error, UnicodeDecodeError) as exc:
            raise ImageError("A7X image is truncated or corrupt") from exc
        if offset != len(data):
            raise ImageError("trailing bytes after A7X image")
        return image

    def save(self, path: Path) -> None:
        path.write_bytes(self.to_bytes())

    @classmethod
    def load(cls, path: Path) -> "Image":
        return cls.from_bytes(path.read_bytes())

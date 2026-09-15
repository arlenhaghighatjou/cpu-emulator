from typing import Protocol

from cpuemulator.arch import ADDRESS_SPACE, IO_BASE


class Device(Protocol):
    base: int
    size: int

    def read(self, offset: int) -> int: ...

    def write(self, offset: int, value: int) -> None: ...

    def reset(self) -> None: ...


class BusFault(Exception):
    def __init__(self, address: int, write: bool) -> None:
        super().__init__(f"{'write to' if write else 'read from'} unmapped address {address:04X}")
        self.address = address
        self.write = write


class Bus:
    def __init__(self) -> None:
        self.ram = bytearray(ADDRESS_SPACE)
        self.devices: list[Device] = []
        self.watches: dict[int, str] = {}
        self.hits: list[tuple[int, str, int]] = []
        self._io: list[tuple[Device, int] | None] = [None] * (ADDRESS_SPACE - IO_BASE)

    def attach(self, device: Device) -> None:
        if device.base < IO_BASE or device.base + device.size > ADDRESS_SPACE:
            raise ValueError(f"device at {device.base:04X} is outside the I/O page")
        for offset in range(device.size):
            slot = device.base - IO_BASE + offset
            if self._io[slot] is not None:
                raise ValueError(f"I/O address {device.base + offset:04X} is already mapped")
            self._io[slot] = (device, offset)
        self.devices.append(device)

    def reset(self) -> None:
        self.ram[:] = bytes(ADDRESS_SPACE)
        self.hits.clear()
        for device in self.devices:
            device.reset()

    def read8(self, address: int) -> int:
        if self.watches:
            value = self._read8(address)
            if "r" in self.watches.get(address, ""):
                self.hits.append((address, "r", value))
            return value
        if address < IO_BASE:
            return self.ram[address]
        return self._read8(address)

    def write8(self, address: int, value: int) -> None:
        if self.watches and "w" in self.watches.get(address, ""):
            self.hits.append((address, "w", value & 0xFF))
        if address < IO_BASE:
            self.ram[address] = value & 0xFF
            return
        slot = self._io[address - IO_BASE]
        if slot is None:
            raise BusFault(address, True)
        slot[0].write(slot[1], value & 0xFF)

    def read16(self, address: int) -> int:
        if address < IO_BASE - 1 and not self.watches:
            return self.ram[address] | self.ram[address + 1] << 8
        return self.read8(address) | self.read8((address + 1) & 0xFFFF) << 8

    def write16(self, address: int, value: int) -> None:
        if address < IO_BASE - 1 and not self.watches:
            self.ram[address] = value & 0xFF
            self.ram[address + 1] = (value >> 8) & 0xFF
            return
        self.write8(address, value & 0xFF)
        self.write8((address + 1) & 0xFFFF, value >> 8)

    def peek8(self, address: int) -> int | None:
        if address < IO_BASE:
            return self.ram[address]
        return None

    def peek16(self, address: int) -> int:
        return self.ram[address & 0xFFFF] | self.ram[(address + 1) & 0xFFFF] << 8

    def load(self, address: int, data: bytes) -> None:
        if address < 0 or address + len(data) > IO_BASE:
            raise ValueError(f"{len(data)} bytes at {address:04X} do not fit in RAM")
        self.ram[address : address + len(data)] = data

    def _read8(self, address: int) -> int:
        if address < IO_BASE:
            return self.ram[address]
        slot = self._io[address - IO_BASE]
        if slot is None:
            raise BusFault(address, False)
        return slot[0].read(slot[1]) & 0xFF

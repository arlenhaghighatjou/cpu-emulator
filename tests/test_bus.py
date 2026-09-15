import pytest

from cpuemulator.bus import Bus, BusFault


class Latch:
    def __init__(self, base: int, size: int = 2) -> None:
        self.base = base
        self.size = size
        self.values = [0] * size

    def read(self, offset: int) -> int:
        return self.values[offset]

    def write(self, offset: int, value: int) -> None:
        self.values[offset] = value

    def reset(self) -> None:
        self.values = [0] * self.size


def test_words_are_little_endian():
    bus = Bus()
    bus.write16(0x2000, 0xBEEF)
    assert bus.ram[0x2000] == 0xEF
    assert bus.ram[0x2001] == 0xBE
    assert bus.read16(0x2000) == 0xBEEF


def test_writes_are_truncated_to_a_byte():
    bus = Bus()
    bus.write8(0x10, 0x1FF)
    assert bus.read8(0x10) == 0xFF


def test_io_page_dispatches_to_devices():
    bus = Bus()
    latch = Latch(0xFF80)
    bus.attach(latch)
    bus.write8(0xFF81, 0x42)
    assert latch.values == [0, 0x42]
    assert bus.read8(0xFF81) == 0x42


def test_unmapped_io_faults():
    bus = Bus()
    with pytest.raises(BusFault):
        bus.read8(0xFF99)
    with pytest.raises(BusFault) as info:
        bus.write8(0xFFFF, 1)
    assert info.value.write


def test_word_spanning_into_io_page_faults():
    bus = Bus()
    with pytest.raises(BusFault):
        bus.read16(0xFEFF)


def test_overlapping_devices_are_rejected():
    bus = Bus()
    bus.attach(Latch(0xFF80, 4))
    with pytest.raises(ValueError):
        bus.attach(Latch(0xFF83))
    with pytest.raises(ValueError):
        bus.attach(Latch(0x8000))


def test_load_rejects_data_that_does_not_fit():
    bus = Bus()
    bus.load(0xFEFE, b"ab")
    with pytest.raises(ValueError):
        bus.load(0xFEFF, b"ab")


def test_watches_record_reads_and_writes():
    bus = Bus()
    bus.watches[0x3000] = "rw"
    bus.watches[0x3001] = "w"
    bus.write16(0x3000, 0x1234)
    bus.read16(0x3000)
    assert bus.hits == [(0x3000, "w", 0x34), (0x3001, "w", 0x12), (0x3000, "r", 0x34)]


def test_reset_clears_ram_and_devices():
    bus = Bus()
    latch = Latch(0xFF80)
    bus.attach(latch)
    bus.write8(0x500, 9)
    bus.write8(0xFF80, 9)
    bus.reset()
    assert bus.read8(0x500) == 0
    assert latch.values == [0, 0]

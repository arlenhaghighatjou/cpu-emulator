from collections import deque

from cpuemulator.arch import (
    IRQ_KEYBOARD,
    IRQ_SERIAL,
    IRQ_TIMER,
    KBD_BASE,
    PIC_BASE,
    RNG_BASE,
    SERIAL_BASE,
    TIMER_BASE,
)

KEY_BUFFER = 16
RNG_TAPS = 0xB400
RNG_DEFAULT = 0xACE1


class InterruptController:
    base = PIC_BASE
    size = 3

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.pending = 0
        self.mask = 0xFF

    def raise_irq(self, irq: int) -> None:
        self.pending |= 1 << irq

    def take(self) -> int:
        active = self.pending & self.mask
        irq = (active & -active).bit_length() - 1
        self.pending &= ~(1 << irq)
        return irq

    def read(self, offset: int) -> int:
        if offset == 0:
            return self.pending
        if offset == 1:
            return self.mask
        return 0

    def write(self, offset: int, value: int) -> None:
        if offset == 1:
            self.mask = value
        elif offset == 2:
            self.pending &= ~value


class Keyboard:
    base = KBD_BASE
    size = 4

    def __init__(self, pic: InterruptController) -> None:
        self.pic = pic
        self.reset()

    def reset(self) -> None:
        self.keys: deque[int] = deque()
        self.overflow = False
        self.ctrl = 0

    def press(self, key: int) -> None:
        if len(self.keys) == KEY_BUFFER:
            self.overflow = True
            return
        self.keys.append(key & 0xFF)
        if self.ctrl & 1:
            self.pic.raise_irq(IRQ_KEYBOARD)

    def type(self, text: str) -> None:
        for char in text:
            self.press(ord(char))

    def read(self, offset: int) -> int:
        match offset:
            case 0:
                status = (1 if self.keys else 0) | (2 if self.overflow else 0)
                self.overflow = False
                return status
            case 1:
                return self.keys.popleft() if self.keys else 0
            case 2:
                return self.ctrl
            case _:
                return len(self.keys)

    def write(self, offset: int, value: int) -> None:
        if offset == 2:
            self.ctrl = value


class Timer:
    base = TIMER_BASE
    size = 6

    def __init__(self, pic: InterruptController) -> None:
        self.pic = pic
        self.reset()

    def reset(self) -> None:
        self.ctrl = 0
        self.status = 0
        self.reload = 0
        self.count = 0

    @property
    def period(self) -> int:
        return self.reload or 0x10000

    def tick(self, cycles: int) -> None:
        if not self.ctrl & 1:
            return
        if cycles < self.count:
            self.count -= cycles
            return
        overshoot = cycles - self.count
        self.status |= 1
        if self.ctrl & 4:
            self.pic.raise_irq(IRQ_TIMER)
        if self.ctrl & 2:
            self.count = self.period - overshoot % self.period
        else:
            self.ctrl &= ~1
            self.count = 0

    def read(self, offset: int) -> int:
        match offset:
            case 0:
                return self.ctrl
            case 1:
                return self.status
            case 2:
                return self.reload & 0xFF
            case 3:
                return self.reload >> 8
            case 4:
                return self.count & 0xFF
            case _:
                return (self.count >> 8) & 0xFF

    def write(self, offset: int, value: int) -> None:
        match offset:
            case 0:
                if value & 1:
                    self.count = self.period
                self.ctrl = value & 7
            case 1:
                self.status &= ~value
            case 2:
                self.reload = (self.reload & 0xFF00) | value
            case 3:
                self.reload = (self.reload & 0x00FF) | value << 8


class Rng:
    base = RNG_BASE
    size = 4

    def __init__(self, seed: int = RNG_DEFAULT) -> None:
        self.seed = seed
        self.reset()

    def reset(self) -> None:
        self.state = self.seed or RNG_DEFAULT
        self.latched = 0
        self._seed_low = 0

    def next(self) -> int:
        lsb = self.state & 1
        self.state >>= 1
        if lsb:
            self.state ^= RNG_TAPS
        return self.state

    def read(self, offset: int) -> int:
        if offset == 0:
            self.latched = self.next()
            return self.latched & 0xFF
        if offset == 1:
            return self.latched >> 8
        return 0

    def write(self, offset: int, value: int) -> None:
        if offset == 2:
            self._seed_low = value
        elif offset == 3:
            self.state = (value << 8 | self._seed_low) or RNG_DEFAULT


class Serial:
    base = SERIAL_BASE
    size = 3

    def __init__(self, pic: InterruptController) -> None:
        self.pic = pic
        self.output = bytearray()
        self.reset()

    def reset(self) -> None:
        self.output.clear()
        self.incoming: deque[int] = deque()
        self.ctrl = 0

    @property
    def text(self) -> str:
        return self.output.decode("latin-1")

    def receive(self, data: bytes) -> None:
        self.incoming.extend(data)
        if data and self.ctrl & 1:
            self.pic.raise_irq(IRQ_SERIAL)

    def read(self, offset: int) -> int:
        match offset:
            case 0:
                return self.incoming.popleft() if self.incoming else 0
            case 1:
                return (1 if self.incoming else 0) | 2
            case _:
                return self.ctrl

    def write(self, offset: int, value: int) -> None:
        if offset == 0:
            self.output.append(value)
        elif offset == 2:
            self.ctrl = value

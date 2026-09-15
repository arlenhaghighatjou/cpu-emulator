import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

from cpuemulator.arch import (
    KEY_BACKSPACE,
    KEY_DOWN,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_UP,
    SCREEN_COLS,
    SCREEN_ROWS,
)
from cpuemulator.display import DEFAULT_ATTR
from cpuemulator.machine import Machine

FRAME = 1 / 60
ANSI_ORDER = (0, 4, 2, 6, 1, 5, 3, 7)
ARROWS = {"A": KEY_UP, "B": KEY_DOWN, "C": KEY_RIGHT, "D": KEY_LEFT}
WINDOWS_ARROWS = {"H": KEY_UP, "P": KEY_DOWN, "M": KEY_RIGHT, "K": KEY_LEFT}
QUIT = object()


def _sgr(attr: int) -> str:
    attr = attr or DEFAULT_ATTR
    fg = attr & 0x0F
    bg = attr >> 4
    fg_code = (90 if fg & 8 else 30) + ANSI_ORDER[fg & 7]
    bg_code = (100 if bg & 8 else 40) + ANSI_ORDER[bg & 7]
    return f"\x1b[{fg_code};{bg_code}m"


def render_row(chars: bytes, attrs: bytes) -> str:
    parts = []
    current = -1
    for char, attr in zip(chars, attrs, strict=True):
        if attr != current:
            parts.append(_sgr(attr))
            current = attr
        parts.append(chr(char) if 0x20 <= char < 0x7F else " ")
    return "".join(parts)


def translate(chars: str) -> list[int]:
    keys = []
    i = 0
    while i < len(chars):
        char = chars[i]
        if char == "\x1b" and chars[i + 1 : i + 2] == "[" and chars[i + 2 : i + 3] in ARROWS:
            keys.append(ARROWS[chars[i + 2]])
            i += 3
            continue
        if char in "\r\n":
            keys.append(KEY_ENTER)
        elif char in "\x08\x7f":
            keys.append(KEY_BACKSPACE)
        elif char == "\x1b":
            keys.append(KEY_ESCAPE)
        elif ord(char) < 0x80:
            keys.append(ord(char))
        i += 1
    return keys


class _WindowsInput:
    def __init__(self) -> None:
        import msvcrt

        self._msvcrt = msvcrt

    def read(self) -> list[int] | object:
        keys = []
        while self._msvcrt.kbhit():
            char = self._msvcrt.getwch()
            if char == "\x03":
                return QUIT
            if char in "\x00\xe0":
                code = self._msvcrt.getwch()
                if code in WINDOWS_ARROWS:
                    keys.append(WINDOWS_ARROWS[code])
                continue
            keys.extend(translate(char))
        return keys


class _PosixInput:
    def read(self) -> list[int] | object:
        import select

        chunks = []
        while select.select([sys.stdin], [], [], 0)[0]:
            data = os.read(sys.stdin.fileno(), 64)
            if not data:
                break
            chunks.append(data.decode("latin-1"))
        return translate("".join(chunks))


@contextmanager
def _console() -> Iterator[None]:
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        saved = None
    else:
        import termios
        import tty

        saved = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if saved is not None:
            import termios

            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)


class Terminal:
    def __init__(self, machine: Machine, hz: int) -> None:
        self.machine = machine
        self.budget = max(1, int(hz * FRAME))
        self._rows: list[tuple[bytes, bytes] | None] = [None] * SCREEN_ROWS
        self._status = ""

    def draw(self) -> None:
        display = self.machine.display
        out = []
        for y in range(SCREEN_ROWS):
            row = (display.row(y), display.attrs(y))
            if row != self._rows[y]:
                self._rows[y] = row
                out.append(f"\x1b[{y + 1};1H{render_row(*row)}")
        status = self.status()
        if status != self._status:
            self._status = status
            out.append(f"\x1b[{SCREEN_ROWS + 1};1H\x1b[0m\x1b[2K{status}")
        if display.cursor_visible:
            x = min(display.cursor_x, SCREEN_COLS - 1) + 1
            y = min(display.cursor_y, SCREEN_ROWS - 1) + 1
            out.append(f"\x1b[{y};{x}H\x1b[?25h")
        else:
            out.append("\x1b[?25l")
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def status(self) -> str:
        cpu = self.machine.cpu
        serial = self.machine.serial.text.rstrip("\n").rsplit("\n", 1)[-1][-40:]
        state = "halted" if cpu.halted else "waiting" if cpu.waiting else "running"
        return f" A7-16  {state:<8} pc={cpu.pc:04X} cycles={cpu.cycles:<12} ctrl+c quits  {serial}"

    def run(self) -> None:
        source = _WindowsInput() if os.name == "nt" else _PosixInput()
        machine = self.machine
        with _console():
            try:
                while True:
                    start = time.perf_counter()
                    keys = source.read()
                    if keys is QUIT:
                        break
                    for key in keys:
                        machine.keyboard.press(key)
                    machine.run(self.budget)
                    self.draw()
                    if machine.cpu.halted:
                        time.sleep(1.5)
                        break
                    spare = FRAME - (time.perf_counter() - start)
                    if spare > 0:
                        time.sleep(spare)
            except KeyboardInterrupt:
                pass

from cpuemulator.arch import ATTR_BASE, DISPLAY_BASE, SCREEN_COLS, SCREEN_ROWS, TEXT_BASE

DEFAULT_ATTR = 0x07

PALETTE = (
    (0x00, 0x00, 0x00),
    (0x00, 0x00, 0xAA),
    (0x00, 0xAA, 0x00),
    (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00),
    (0xAA, 0x00, 0xAA),
    (0xAA, 0x55, 0x00),
    (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55),
    (0x55, 0x55, 0xFF),
    (0x55, 0xFF, 0x55),
    (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55),
    (0xFF, 0x55, 0xFF),
    (0xFF, 0xFF, 0x55),
    (0xFF, 0xFF, 0xFF),
)


class Display:
    base = DISPLAY_BASE
    size = 5

    def __init__(self, ram: bytearray) -> None:
        self.ram = ram
        self.reset()

    def reset(self) -> None:
        self.cursor_x = 0
        self.cursor_y = 0
        self.ctrl = 0

    @property
    def cursor_visible(self) -> bool:
        return bool(self.ctrl & 1)

    def read(self, offset: int) -> int:
        match offset:
            case 0:
                return self.cursor_x
            case 1:
                return self.cursor_y
            case 2:
                return self.ctrl
            case 3:
                return SCREEN_COLS
            case _:
                return SCREEN_ROWS

    def write(self, offset: int, value: int) -> None:
        match offset:
            case 0:
                self.cursor_x = value
            case 1:
                self.cursor_y = value
            case 2:
                self.ctrl = value

    def row(self, y: int) -> bytes:
        start = TEXT_BASE + y * SCREEN_COLS
        return bytes(self.ram[start : start + SCREEN_COLS])

    def attrs(self, y: int) -> bytes:
        start = ATTR_BASE + y * SCREEN_COLS
        return bytes(self.ram[start : start + SCREEN_COLS])

    def text(self, y: int) -> str:
        return "".join(chr(c) if 0x20 <= c < 0x7F else " " for c in self.row(y))

    def lines(self) -> list[str]:
        return [self.text(y) for y in range(SCREEN_ROWS)]

    def dump(self) -> str:
        return "\n".join(line.rstrip() for line in self.lines()).rstrip("\n")

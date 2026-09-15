import time
import tkinter as tk
from tkinter import font as tkfont

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
from cpuemulator.display import DEFAULT_ATTR, PALETTE
from cpuemulator.machine import Machine

FRAME_MS = 16
KEYSYMS = {
    "Up": KEY_UP,
    "Down": KEY_DOWN,
    "Left": KEY_LEFT,
    "Right": KEY_RIGHT,
    "Return": KEY_ENTER,
    "KP_Enter": KEY_ENTER,
    "BackSpace": KEY_BACKSPACE,
    "Escape": KEY_ESCAPE,
}
COLORS = tuple(f"#{r:02x}{g:02x}{b:02x}" for r, g, b in PALETTE)


class Window:
    def __init__(self, machine: Machine, hz: int, size: int = 16) -> None:
        self.machine = machine
        self.budget = max(1, hz * FRAME_MS // 1000)
        self.root = tk.Tk()
        self.root.title("A7-16")
        self.root.configure(background="black")
        self.font = tkfont.Font(family="Courier New", size=size, weight="bold")
        self.cell_w = self.font.measure("W")
        self.cell_h = self.font.metrics("linespace")
        width = self.cell_w * SCREEN_COLS
        height = self.cell_h * SCREEN_ROWS
        self.canvas = tk.Canvas(
            self.root, width=width, height=height, background="black", highlightthickness=0
        )
        self.canvas.pack(padx=12, pady=12)
        self.status = tk.Label(
            self.root,
            anchor="w",
            background="black",
            foreground="#888888",
            font=("Courier New", 10),
        )
        self.status.pack(fill="x", padx=12, pady=(0, 8))
        self._backs = []
        self._glyphs = []
        for y in range(SCREEN_ROWS):
            for x in range(SCREEN_COLS):
                left = x * self.cell_w
                top = y * self.cell_h
                self._backs.append(
                    self.canvas.create_rectangle(
                        left, top, left + self.cell_w, top + self.cell_h, width=0, fill="black"
                    )
                )
                self._glyphs.append(
                    self.canvas.create_text(left, top, anchor="nw", text=" ", font=self.font)
                )
        self._cursor = self.canvas.create_rectangle(0, 0, 0, 0, width=0, fill=COLORS[7])
        self._cells: list[tuple[int, int] | None] = [None] * (SCREEN_COLS * SCREEN_ROWS)
        self._last = time.perf_counter()
        self._cycles = 0
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def on_key(self, event: tk.Event) -> None:
        keyboard = self.machine.keyboard
        if event.keysym in KEYSYMS:
            keyboard.press(KEYSYMS[event.keysym])
        elif len(event.char) == 1 and ord(event.char) < 0x80:
            keyboard.press(ord(event.char))

    def draw(self) -> None:
        display = self.machine.display
        canvas = self.canvas
        for y in range(SCREEN_ROWS):
            chars = display.row(y)
            attrs = display.attrs(y)
            base = y * SCREEN_COLS
            for x in range(SCREEN_COLS):
                cell = (chars[x], attrs[x] or DEFAULT_ATTR)
                index = base + x
                if self._cells[index] == cell:
                    continue
                self._cells[index] = cell
                char, attr = cell
                canvas.itemconfigure(self._backs[index], fill=COLORS[attr >> 4])
                glyph = chr(char) if 0x20 <= char < 0x7F else " "
                canvas.itemconfigure(self._glyphs[index], text=glyph, fill=COLORS[attr & 0x0F])
        if (
            display.cursor_visible
            and display.cursor_x < SCREEN_COLS
            and display.cursor_y < SCREEN_ROWS
        ):
            left = display.cursor_x * self.cell_w
            bottom = (display.cursor_y + 1) * self.cell_h
            canvas.coords(self._cursor, left, bottom - 3, left + self.cell_w, bottom)
        else:
            canvas.coords(self._cursor, 0, 0, 0, 0)
        canvas.tag_raise(self._cursor)

    def update_status(self) -> None:
        cpu = self.machine.cpu
        now = time.perf_counter()
        rate = (cpu.cycles - self._cycles) / max(now - self._last, 1e-6)
        self._last = now
        self._cycles = cpu.cycles
        state = cpu.fault or ("halted" if cpu.halted else "waiting" if cpu.waiting else "running")
        self.status.configure(
            text=f"{state}   pc={cpu.pc:04X}   cycles={cpu.cycles}   {rate / 1000:,.0f} kHz"
        )

    def tick(self) -> None:
        self.machine.run(self.budget)
        self.draw()
        self.update_status()
        if not self.machine.cpu.halted:
            self.root.after(FRAME_MS, self.tick)

    def run(self) -> None:
        self.root.after(0, self.tick)
        self.root.mainloop()

import cmd
import shlex
from pathlib import Path
from typing import TextIO

from cpuemulator.arch import (
    KEY_BACKSPACE,
    KEY_DOWN,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_UP,
)
from cpuemulator.debugger import REGISTER_INDEX, Debugger

KEY_NAMES = {
    "enter": KEY_ENTER,
    "esc": KEY_ESCAPE,
    "backspace": KEY_BACKSPACE,
    "up": KEY_UP,
    "down": KEY_DOWN,
    "left": KEY_LEFT,
    "right": KEY_RIGHT,
    "space": 0x20,
}


def _number(text: str) -> int:
    return int(text, 0)


class Shell(cmd.Cmd):
    prompt = "(a7) "
    intro = "A7-16 debugger. Type help for commands."

    def __init__(self, debugger: Debugger, stdout: TextIO | None = None) -> None:
        super().__init__(stdout=stdout)
        self.debugger = debugger
        self.use_rawinput = stdout is None

    def emit(self, text: str) -> None:
        if text:
            self.stdout.write(text + "\n")

    def onecmd(self, line: str) -> bool:
        try:
            return super().onecmd(line)
        except (ValueError, IndexError) as exc:
            self.emit(f"error: {exc}")
            return False

    def default(self, line: str) -> None:
        self.emit(f"unknown command '{line.split()[0]}'")

    def _show_stop(self, reason: str | None) -> None:
        if reason:
            self.emit(reason)
        self.emit(self.debugger.current())

    def do_step(self, arg: str) -> None:
        """step [n]: execute n instructions"""
        self._show_stop(self.debugger.step(_number(arg) if arg else 1))

    def do_next(self, arg: str) -> None:
        """next: step over calls and software interrupts"""
        self._show_stop(self.debugger.next())

    def do_finish(self, arg: str) -> None:
        """finish: run until the current function returns"""
        self._show_stop(self.debugger.finish())

    def do_continue(self, arg: str) -> None:
        """continue [cycles]: run until a breakpoint, watch, halt or cycle limit"""
        self._show_stop(self.debugger.cont(_number(arg) if arg else None))

    def do_break(self, arg: str) -> None:
        """break [address|symbol]: add a breakpoint or list them"""
        debugger = self.debugger
        if not arg:
            for address in sorted(debugger.breakpoints):
                self.emit(debugger.location(address))
            return
        address = debugger.resolve(arg)
        debugger.breakpoints.add(address)
        self.emit(f"breakpoint at {debugger.location(address)}")

    def do_delete(self, arg: str) -> None:
        """delete [address|symbol]: remove one breakpoint or all of them"""
        if not arg:
            self.debugger.breakpoints.clear()
            return
        self.debugger.breakpoints.discard(self.debugger.resolve(arg))

    def do_watch(self, arg: str) -> None:
        """watch [address [r|w|rw]]: stop when memory is accessed, or list watches"""
        watches = self.debugger.machine.bus.watches
        if not arg:
            for address, kind in sorted(watches.items()):
                self.emit(f"{address:04X} {kind}")
            return
        parts = arg.split()
        kind = parts[1] if len(parts) > 1 else "w"
        self.debugger.watch(self.debugger.resolve(parts[0]), kind)

    def do_unwatch(self, arg: str) -> None:
        """unwatch address: remove a watch"""
        self.debugger.unwatch(self.debugger.resolve(arg))

    def do_regs(self, arg: str) -> None:
        """regs: show registers, flags and cycle count"""
        self.emit(self.debugger.registers())

    def do_flags(self, arg: str) -> None:
        """flags: show the status flags"""
        self.emit(f"{self.debugger.cpu.flags:04X} [{self.debugger.flags()}]")

    def do_stack(self, arg: str) -> None:
        """stack [n]: show n words from the top of the stack"""
        self.emit(self.debugger.stack(_number(arg) if arg else 8))

    def do_x(self, arg: str) -> None:
        """x address [length]: hexdump memory"""
        parts = arg.split()
        length = _number(parts[1]) if len(parts) > 1 else 64
        self.emit(self.debugger.hexdump(self.debugger.resolve(parts[0]), length))

    def do_dis(self, arg: str) -> None:
        """dis [address [count]]: disassemble, around pc by default"""
        parts = arg.split()
        address = self.debugger.resolve(parts[0]) if parts else None
        count = _number(parts[1]) if len(parts) > 1 else 10
        self.emit(self.debugger.disassembly(address, count))

    def do_trace(self, arg: str) -> None:
        """trace on [file] | off | show [n]: record executed instructions"""
        parts = arg.split()
        debugger = self.debugger
        action = parts[0] if parts else "show"
        if action == "on":
            debugger.start_trace(Path(parts[1]) if len(parts) > 1 else None)
        elif action == "off":
            debugger.stop_trace()
        elif action == "show":
            count = _number(parts[1]) if len(parts) > 1 else 20
            for line in list(debugger.history)[-count:]:
                self.emit(line)
        else:
            raise ValueError("trace takes on, off or show")

    def do_stats(self, arg: str) -> None:
        """stats: execution statistics"""
        self.emit(self.debugger.stats())

    def do_set(self, arg: str) -> None:
        """set register|pc value: change a register"""
        name, value = arg.split()
        cpu = self.debugger.cpu
        number = self.debugger.resolve(value)
        if name.lower() == "pc":
            cpu.pc = number
        elif name.lower() in REGISTER_INDEX:
            cpu.reg[REGISTER_INDEX[name.lower()]] = number
        else:
            raise ValueError(f"unknown register '{name}'")

    def do_poke(self, arg: str) -> None:
        """poke address byte...: write bytes to memory"""
        parts = arg.split()
        address = self.debugger.resolve(parts[0])
        for offset, value in enumerate(parts[1:]):
            self.debugger.machine.bus.write8((address + offset) & 0xFFFF, _number(value))

    def do_key(self, arg: str) -> None:
        """key "text" | enter | up | ...: press keys on the emulated keyboard"""
        keyboard = self.debugger.machine.keyboard
        for word in shlex.split(arg):
            if word.lower() in KEY_NAMES:
                keyboard.press(KEY_NAMES[word.lower()])
            else:
                keyboard.type(word)

    def do_screen(self, arg: str) -> None:
        """screen: print the text framebuffer"""
        self.emit(self.debugger.machine.display.dump())

    def do_serial(self, arg: str) -> None:
        """serial: print bytes sent to the serial port"""
        self.emit(self.debugger.machine.serial.text)

    def do_symbols(self, arg: str) -> None:
        """symbols [filter]: list labels"""
        symbols = self.debugger.machine.image.symbols
        for name, value in sorted(symbols.items(), key=lambda item: item[1]):
            if arg in name:
                self.emit(f"{value:04X}  {name}")

    def do_reset(self, arg: str) -> None:
        """reset: reload the program and reset the machine"""
        self.debugger.reload()
        self.emit(self.debugger.current())

    def do_quit(self, arg: str) -> bool:
        """quit: leave the debugger"""
        return True

    do_EOF = do_quit
    do_s = do_step
    do_n = do_next
    do_c = do_continue
    do_b = do_break
    do_q = do_quit

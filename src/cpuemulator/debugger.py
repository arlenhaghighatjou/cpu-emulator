from collections import deque
from pathlib import Path

from cpuemulator.arch import FLAG_C, FLAG_I, FLAG_N, FLAG_V, FLAG_Z, IO_BASE, REGISTER_ALIASES
from cpuemulator.cpu import CPU
from cpuemulator.decoder import decode
from cpuemulator.disassembler import disassemble, format_instruction, label_names
from cpuemulator.instructions import BY_CODE
from cpuemulator.machine import Machine

FLAG_LETTERS = ((FLAG_I, "I"), (FLAG_V, "V"), (FLAG_N, "N"), (FLAG_Z, "Z"), (FLAG_C, "C"))
REGISTER_INDEX = {f"r{i}": i for i in range(8)} | REGISTER_ALIASES


class Debugger:
    def __init__(self, machine: Machine) -> None:
        self.machine = machine
        self.breakpoints: set[int] = set()
        self.history: deque[str] = deque(maxlen=256)
        self.tracing = False
        self.trace_path: Path | None = None
        self._pending: list[str] = []
        self.names = label_names(machine.image.symbols)

    @property
    def cpu(self) -> CPU:
        return self.machine.cpu

    def start_trace(self, path: Path | None = None) -> None:
        self.stop_trace()
        self.tracing = True
        self.trace_path = path
        if path is not None:
            path.write_text("", encoding="utf-8")

    def stop_trace(self) -> None:
        self.flush_trace()
        self.tracing = False
        self.trace_path = None

    def flush_trace(self) -> None:
        if self.trace_path is None or not self._pending:
            return
        with self.trace_path.open("a", encoding="utf-8") as out:
            out.write("\n".join(self._pending) + "\n")
        self._pending.clear()

    def reload(self) -> None:
        self.machine.reset()
        self.names = label_names(self.machine.image.symbols)
        self.history.clear()

    def resolve(self, text: str) -> int:
        text = text.strip()
        lowered = text.lower()
        if lowered in REGISTER_INDEX:
            return self.cpu.reg[REGISTER_INDEX[lowered]]
        if lowered == "pc":
            return self.cpu.pc
        offset = 0
        for sign in ("+", "-"):
            if sign in text[1:]:
                head, _, tail = text.rpartition(sign)
                offset = self.resolve(tail) * (1 if sign == "+" else -1)
                text = head.strip()
                break
        symbols = self.machine.image.symbols
        if text in symbols:
            return (symbols[text] + offset) & 0xFFFF
        try:
            value = int(text, 0) if text.lower().startswith(("0x", "0b", "0o")) else int(text, 16)
        except ValueError:
            raise ValueError(f"unknown address or symbol '{text}'") from None
        return (value + offset) & 0xFFFF

    def location(self, address: int) -> str:
        best = None
        for name, value in self.machine.image.symbols.items():
            if value <= address and address - value < 0x400 and (best is None or value > best[1]):
                best = (name, value)
        if best is None:
            return f"{address:04X}"
        delta = address - best[1]
        suffix = f"+{delta}" if delta else ""
        return f"{address:04X} <{best[0]}{suffix}>"

    def current(self) -> str:
        cpu = self.cpu
        instruction = decode(self.machine.bus.peek16, cpu.pc)
        if instruction is None:
            return f"{cpu.pc:04X}  .dw 0x{self.machine.bus.peek16(cpu.pc):04X}"
        words = " ".join(f"{w:04X}" for w in (instruction.word, *instruction.operands))
        text = format_instruction(instruction, self.names)
        return f"{self.location(cpu.pc)}  {words:<14}  {text}"

    def _record(self) -> None:
        cpu = self.cpu
        registers = " ".join(f"{v:04X}" for v in cpu.reg)
        line = f"{cpu.cycles:>10}  {self.current():<48}  {registers}  {self.flags()}"
        self.history.append(line)
        if self.trace_path is not None:
            self._pending.append(line)
            if len(self._pending) >= 4096:
                self.flush_trace()

    def step(self, count: int = 1) -> str | None:
        for _ in range(count):
            reason = self._single()
            if reason:
                return reason
        return None

    def _single(self) -> str | None:
        cpu = self.cpu
        if cpu.halted:
            return self._halt_reason()
        if self.tracing:
            self._record()
        bus = self.machine.bus
        bus.hits.clear()
        self.machine.step()
        if bus.hits:
            address, kind, value = bus.hits[0]
            access = "read" if kind == "r" else "write"
            return f"watch {access} {address:04X} = {value:02X}"
        if cpu.halted:
            return self._halt_reason()
        return None

    def _halt_reason(self) -> str:
        return f"fault: {self.cpu.fault}" if self.cpu.fault else "halted"

    def cont(self, limit: int | None = None) -> str:
        cpu = self.cpu
        start = cpu.cycles
        first = True
        while True:
            if not first and cpu.pc in self.breakpoints:
                return f"breakpoint at {self.location(cpu.pc)}"
            first = False
            if self.machine.idle:
                return "waiting for an interrupt"
            reason = self._single()
            if reason:
                return reason
            if limit is not None and cpu.cycles - start >= limit:
                return f"stopped after {cpu.cycles - start} cycles"

    def next(self) -> str | None:
        cpu = self.cpu
        instruction = decode(self.machine.bus.peek16, cpu.pc)
        if instruction is None or instruction.op.name not in ("call", "int"):
            return self.step()
        return self._run_to(cpu.pc + instruction.size, cpu.sp)

    def finish(self) -> str | None:
        cpu = self.cpu
        depth = cpu.sp
        while True:
            instruction = decode(self.machine.bus.peek16, cpu.pc)
            reason = self._single()
            if reason:
                return reason
            if instruction and instruction.op.name in ("ret", "iret") and cpu.sp > depth:
                return None
            if cpu.pc in self.breakpoints:
                return f"breakpoint at {self.location(cpu.pc)}"

    def _run_to(self, address: int, sp: int) -> str | None:
        cpu = self.cpu
        while True:
            reason = self._single()
            if reason:
                return reason
            if cpu.pc == address and cpu.sp >= sp:
                return None
            if cpu.pc in self.breakpoints:
                return f"breakpoint at {self.location(cpu.pc)}"

    def flags(self) -> str:
        flags = self.cpu.flags
        return "".join(letter if flags & bit else "-" for bit, letter in FLAG_LETTERS)

    def registers(self) -> str:
        cpu = self.cpu
        names = ("r0", "r1", "r2", "r3", "r4", "r5", "fp", "sp")
        rows = [
            "  ".join(f"{names[i]}={cpu.reg[i]:04X}" for i in range(0, 4)),
            "  ".join(f"{names[i]}={cpu.reg[i]:04X}" for i in range(4, 8)),
            f"pc={cpu.pc:04X}  flags={cpu.flags:04X} [{self.flags()}]  cycles={cpu.cycles}",
        ]
        if cpu.waiting:
            rows.append("state: waiting for interrupt")
        if cpu.halted:
            rows.append(f"state: {self._halt_reason()}")
        return "\n".join(rows)

    def stack(self, count: int = 8) -> str:
        cpu = self.cpu
        rows = []
        for i in range(count):
            address = (cpu.sp + 2 * i) & 0xFFFF
            if address >= IO_BASE - 1:
                break
            value = self.machine.bus.peek16(address)
            marker = "sp ->" if i == 0 else "     "
            label = self.names.get(value, "")
            rows.append(f"{marker} {address:04X}: {value:04X}  {label}".rstrip())
        return "\n".join(rows)

    def hexdump(self, address: int, length: int = 64) -> str:
        rows = []
        bus = self.machine.bus
        for start in range(address, min(address + length, 0x10000), 16):
            values = [
                bus.peek8(a) for a in range(start, min(start + 16, address + length, 0x10000))
            ]
            hexes = " ".join("??" if v is None else f"{v:02X}" for v in values)
            text = "".join(chr(v) if v is not None and 0x20 <= v < 0x7F else "." for v in values)
            rows.append(f"{start:04X}  {hexes:<47}  {text}")
        return "\n".join(rows)

    def disassembly(self, address: int | None = None, count: int = 10) -> str:
        pc = self.cpu.pc
        address = pc if address is None else address
        rows = []
        read = self.machine.bus.peek16
        for at, words, text in disassemble(read, address, count, self.names):
            if at in self.names and not self.names[at].count("."):
                rows.append(f"{self.names[at]}:")
            marker = ("=>" if at == pc else "  ") + ("*" if at in self.breakpoints else " ")
            hexes = " ".join(f"{w:04X}" for w in words)
            rows.append(f"{marker} {at:04X}  {hexes:<14}  {text}")
        return "\n".join(rows)

    def watch(self, address: int, kind: str) -> None:
        if kind not in ("r", "w", "rw"):
            raise ValueError("watch kind must be r, w or rw")
        self.machine.bus.watches[address] = kind

    def unwatch(self, address: int) -> None:
        self.machine.bus.watches.pop(address, None)

    def stats(self, top: int = 12) -> str:
        cpu = self.cpu
        rows = [
            f"instructions  {cpu.instructions}",
            f"cycles        {cpu.cycles}",
            f"interrupts    {cpu.interrupts}",
        ]
        counts = sorted(
            ((count, BY_CODE[code].name) for code, count in enumerate(cpu.op_counts) if count),
            reverse=True,
        )
        total = cpu.instructions or 1
        for count, name in counts[:top]:
            rows.append(f"  {name:<6} {count:>10}  {100 * count / total:5.1f}%")
        return "\n".join(rows)

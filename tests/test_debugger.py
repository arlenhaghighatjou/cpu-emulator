import io

import pytest

from cpuemulator.asm import assemble
from cpuemulator.debugger import Debugger
from cpuemulator.machine import Machine
from cpuemulator.shell import Shell

PROGRAM = """
start:
    mov r0, 3
    call double
    call double
    mov [result], r0
    halt
double:
    push r1
    mov r1, r0
    add r0, r1
    pop r1
    ret
result: .dw 0
"""


@pytest.fixture
def debugger() -> Debugger:
    machine = Machine(seed=1)
    machine.load(assemble(PROGRAM))
    return Debugger(machine)


def test_resolve_symbols_offsets_registers_and_hex(debugger):
    symbols = debugger.machine.image.symbols
    assert debugger.resolve("double") == symbols["double"]
    assert debugger.resolve("double+4") == symbols["double"] + 4
    assert debugger.resolve("0x20") == 0x20
    assert debugger.resolve("1F0") == 0x1F0
    assert debugger.resolve("sp") == 0xE000
    with pytest.raises(ValueError, match="unknown address"):
        debugger.resolve("nowhere")


def test_breakpoint_stops_before_the_instruction(debugger):
    debugger.breakpoints.add(debugger.resolve("double"))
    assert debugger.cont().startswith("breakpoint at")
    assert debugger.cpu.pc == debugger.resolve("double")
    assert debugger.cont().startswith("breakpoint at")
    assert debugger.cont() == "halted"
    assert debugger.machine.bus.read16(debugger.resolve("result")) == 12


def test_next_steps_over_calls(debugger):
    debugger.step()
    assert debugger.next() is None
    assert debugger.cpu.reg[0] == 6
    assert debugger.cpu.pc == debugger.resolve("start") + 8


def test_finish_returns_to_the_caller(debugger):
    debugger.step(2)
    assert debugger.cpu.pc == debugger.resolve("double")
    assert debugger.finish() is None
    assert debugger.cpu.pc == debugger.resolve("start") + 8
    assert debugger.cpu.reg[0] == 6


def test_write_watch_reports_the_access(debugger):
    debugger.watch(debugger.resolve("result"), "w")
    assert debugger.cont() == f"watch write {debugger.resolve('result'):04X} = 0C"


def test_trace_records_history(debugger):
    debugger.tracing = True
    debugger.step(3)
    assert len(debugger.history) == 3
    assert "mov r0, 3" in debugger.history[0]
    assert "call double" in debugger.history[1]
    assert "push r1" in debugger.history[2]


def test_stack_view_names_return_addresses(debugger):
    debugger.step(3)
    lines = debugger.stack(2).splitlines()
    assert lines[0].startswith("sp -> DFFC:")
    assert lines[1].startswith("      DFFE:")


def test_disassembly_marks_pc_and_breakpoints(debugger):
    debugger.breakpoints.add(debugger.resolve("start") + 4)
    lines = debugger.disassembly(count=2).splitlines()
    assert lines[0] == "start:"
    assert lines[1].startswith("=>  0100")
    assert lines[2].startswith("  * 0104")
    assert lines[2].endswith("call double")


def test_hexdump_shows_ascii_and_io_holes(debugger):
    debugger.machine.bus.load(0x3000, b"Hi!\x00")
    assert debugger.hexdump(0x3000, 4) == "3000  48 69 21 00" + " " * 38 + "Hi!."
    assert "??" in debugger.hexdump(0xFF00, 2)


def test_stats_count_opcodes(debugger):
    debugger.cont()
    stats = debugger.stats()
    assert "instructions  " in stats
    assert "mov" in stats


def test_halted_fault_is_reported():
    machine = Machine(seed=1)
    machine.load(assemble("mov r0, 1\ndiv r0, 0"))
    debugger = Debugger(machine)
    assert debugger.cont() == "fault: unhandled divide by zero at 0104"


def run_shell(debugger: Debugger, *commands: str) -> str:
    out = io.StringIO()
    shell = Shell(debugger, stdout=out)
    for command in commands:
        shell.onecmd(command)
    return out.getvalue()


def test_shell_commands(debugger):
    output = run_shell(debugger, "break double", "c", "regs", "s 2", "set r5 0x1234", "flags")
    assert "breakpoint at" in output
    assert "pc=" in output
    assert debugger.cpu.reg[5] == 0x1234


def test_shell_reports_errors_without_crashing(debugger):
    output = run_shell(debugger, "x nowhere", "frobnicate", "set r9 1")
    assert "error: unknown address or symbol 'nowhere'" in output
    assert "unknown command 'frobnicate'" in output
    assert "error: unknown register 'r9'" in output


def test_shell_key_presses_reach_the_keyboard(debugger):
    run_shell(debugger, 'key "12" enter up')
    assert list(debugger.machine.keyboard.keys) == [0x31, 0x32, 0x0D, 0x80]

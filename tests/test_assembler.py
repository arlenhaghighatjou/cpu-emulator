import pytest

from cpuemulator.asm import AsmError, Assembler, assemble, assemble_file
from cpuemulator.instructions import BY_NAME, BYTE, Mode, encode
from cpuemulator.machine import Machine


def code(source: str) -> list[int]:
    image = assemble(source)
    data = b"".join(chunk for _, chunk in image.segments)
    return [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]


def op(name: str, mode: int = 0, rd: int = 0, rs: int = 0) -> int:
    return encode(BY_NAME[name].code, mode, rd, rs)


def run(source: str, budget: int = 100_000) -> Machine:
    machine = Machine(seed=1)
    machine.load(assemble(source))
    machine.run(budget)
    return machine


@pytest.mark.parametrize(
    ("source", "words"),
    [
        ("nop", [op("nop")]),
        ("mov r1, r2", [op("mov", Mode.REG, 1, 2)]),
        ("mov r1, -1", [op("mov", Mode.IMM, 1), 0xFFFF]),
        ("mov r1, [r2]", [op("mov", Mode.IND, 1, 2)]),
        ("mov r1, byte [0x4000]", [op("mov", Mode.ABS | BYTE, 1), 0x4000]),
        ("mov r1, [sp + 4]", [op("mov", Mode.IDX, 1, 7), 4]),
        ("mov [r3 + 2], r1", [op("store", Mode.IDX, 3, 1), 2]),
        ("mov byte [0x10], 'A'", [op("storei", Mode.ABS | BYTE, 0), 0x10, 0x41]),
        ("mov word [fp], 7", [op("storei", Mode.IND, 6), 7]),
        ("lea r0, [fp - 2]", [op("lea", Mode.IDX, 0, 6), 0xFFFE]),
        ("xchg r4, r5", [op("xchg", 0, 4, 5)]),
        ("inc fp", [op("inc", 0, 6)]),
        ("push 0x1234", [op("push", Mode.IMM), 0x1234]),
        ("push byte [r1]", [op("push", Mode.IND | BYTE, 0, 1)]),
        ("call r2", [op("call", Mode.REG, 0, 2)]),
        ("jmp r3", [op("j", 0, 1, 3)]),
        ("jz 0x200", [op("j", 1, 0), 0x200]),
        ("jge 0x200", [op("j", 11, 0), 0x200]),
        ("int 31", [op("int", 0, 3, 7)]),
        ("in r0, 0x01", [op("in", Mode.IMM, 0), 1]),
        ("out r2, r0", [op("out", Mode.REG, 0, 2)]),
        ("iret", [op("iret")]),
    ],
)
def test_instruction_encoding(source, words):
    assert code(source) == words


def test_forward_references_and_current_address():
    words = code("jmp end\nhere: .dw $\nend: halt")
    assert words == [op("j", 0, 0), 0x106, 0x104, op("halt")]


def test_local_labels_are_scoped_to_the_previous_global_label():
    source = """
    first:
    .loop: jmp .loop
    second:
    .loop: jmp .loop
    jmp first.loop
    """
    image = assemble(source)
    assert image.symbols["first.loop"] == 0x100
    assert image.symbols["second.loop"] == 0x104
    assert code(source)[1::2] == [0x100, 0x104, 0x100]


def test_constants_and_expressions():
    words = code(
        """
        COLS = 80
        .equ ROWS, 25
        CELLS = COLS * ROWS
        .dw CELLS, -7 / 2, -7 % 2, 1 << 4 | 3, ~0 & 0xFF, (3 + 4) * 2
        """
    )
    assert words == [2000, 0xFFFD, 0xFFFF, 19, 0xFF, 14]


def test_data_directives_and_org():
    image = assemble(
        """
        .org 0x2000
        .db 1, "AB", 'C'
        .asciz "hi"
        .align 4
        .ds 3, 0xEE
        .dw "Z"
        """
    )
    assert image.segments == [
        (0x2000, b"\x01ABChi\x00"),
        (0x2008, b"\xee\xee\xee\x5a\x00"),
    ]


def test_entry_defaults_to_first_output_and_can_be_set():
    assert assemble(".org 0x300\nnop").entry == 0x300
    assert assemble(".org 0x300\nnop\nmain: halt\n.entry main").entry == 0x302


def test_line_map_and_listing():
    assembler = Assembler()
    image = assembler.assemble("start:\n  mov r0, 1\n  halt\n", "demo.asm")
    assert image.source(0x100) == ("demo.asm", 2)
    assert image.source(0x104) == ("demo.asm", 3)
    listing = assembler.listing_text().splitlines()
    assert listing[0] == "0100  40 0C 01 00          mov r0, 1"
    assert listing[1] == "0104  00 04                halt"


def test_includes_resolve_relative_to_the_including_file(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "consts.inc").write_text("ANSWER = 42\n")
    (tmp_path / "main.asm").write_text('.include "lib/consts.inc"\nmov r0, ANSWER\n')
    image = assemble_file(tmp_path / "main.asm")
    assert image.segments[0][1][2:4] == (42).to_bytes(2, "little")


def test_recursive_include_is_an_error(tmp_path):
    (tmp_path / "a.asm").write_text('.include "b.asm"\n')
    (tmp_path / "b.asm").write_text('.include "a.asm"\n')
    with pytest.raises(AsmError, match="recursive include"):
        assemble_file(tmp_path / "a.asm")


def test_hardware_library_is_on_the_include_path():
    image = assemble('.include "lib/hw.inc"\nmov r0, KBD_STATUS')
    assert image.segments[0][1][2] == 0x00


@pytest.mark.parametrize(
    ("source", "message", "line"),
    [
        ("nop\nfoo r0", "unknown instruction 'foo'", 2),
        ("mov r0, missing", "undefined symbol 'missing'", 1),
        ("a:\na:", "'a' is already defined", 2),
        (".org later\nlater:", "'later' must be defined before it is used here", 1),
        ("mov r0", "'mov' takes 2 operands, got 1", 1),
        ("add [r0], r1", "destination of 'add' must be a register, not a memory operand", 1),
        ("mov [r0], [r1]", "cannot move memory to memory, load it into a register", 1),
        ("mov r0, 0x10000", "value 65536 does not fit in 16 bits", 1),
        ("mov byte [r0], 300", "value 300 does not fit in a byte", 1),
        ("int 3", "software interrupt vector 3 is outside 8-31", 1),
        ("in r0, 256", "port 256 is outside 0-255", 1),
        ("jmp [r0]", "jump target must be an address or a register", 1),
        ("lea r0, byte [r1]", "lea needs an unsized memory operand", 1),
        (".org 0xFEFF\n.dw 1", "code at FEFF runs into the I/O page", 2),
        (".org 0x200\nnop\n.org 0x200\nhalt", "bytes at 0200 overlap earlier output", 4),
        (".bogus 1", "unknown directive '.bogus'", 1),
        ("A = B\nB = A\nmov r0, A", "constant 'A' refers to itself", 2),
        (".dw 1 / 0", "division by zero in expression", 1),
        (".ascii 5", ".ascii takes quoted strings", 1),
    ],
)
def test_errors_carry_line_numbers(source, message, line):
    with pytest.raises(AsmError) as info:
        assemble(source, "bad.asm")
    assert info.value.message == message
    assert info.value.line == line
    assert info.value.file == "bad.asm"


def test_assembled_program_runs_on_the_machine():
    machine = run(
        """
        start:
            mov r0, 0
            mov r1, 10
        .loop:
            add r0, r1
            dec r1
            jnz .loop
            mov [result], r0
            halt
        result: .dw 0
        """
    )
    assert machine.cpu.halted
    assert machine.cpu.fault is None
    assert machine.bus.read16(machine.image.symbols["result"]) == 55


def test_machine_fast_forwards_idle_time_to_the_timer():
    machine = run(
        """
        .include "lib/hw.inc"
        .org VEC_TIMER * 2
        .dw tick
        .org 0x100
        start:
            .entry start
            mov r0, 100
            out TIMER_RELOAD_L, r0
            mov r0, 0
            out TIMER_RELOAD_H, r0
            mov r0, TIMER_ENABLE | TIMER_PERIODIC | TIMER_IRQ
            out TIMER_CTRL, r0
            sti
        .idle:
            wait
            cmp r5, 3
            jne .idle
            halt
        tick:
            inc r5
            iret
        """,
        budget=1_000_000,
    )
    assert machine.cpu.reg[5] == 3
    assert machine.cpu.halted
    assert 300 <= machine.cpu.cycles < 400

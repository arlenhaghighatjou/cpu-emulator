import pytest

from cpuemulator.asm import assemble
from cpuemulator.bus import Bus
from cpuemulator.disassembler import disassemble, label_names


def load(source: str) -> tuple[Bus, dict[str, int]]:
    image = assemble(source)
    bus = Bus()
    for address, data in image.segments:
        bus.load(address, data)
    return bus, image.symbols


@pytest.mark.parametrize(
    "line",
    [
        "nop",
        "mov r1, r2",
        "mov r1, 7",
        "mov r1, 0xBEEF",
        "add fp, [sp]",
        "sub r0, byte [0x4000]",
        "cmp r3, [r2 + 0x0010]",
        "mov r0, word [fp - 4]",
        "mov [r3 + 2], r1",
        "mov byte [0x0010], 0x0041",
        "mov word [fp], 7",
        "lea r0, [fp - 2]",
        "xchg r4, r5",
        "neg r2",
        "push byte [r1]",
        "pop sp",
        "call r2",
        "call [0x2000]",
        "jmp r3",
        "jle 0x0200",
        "int 17",
        "in r0, 0x0050",
        "out r2, r0",
        "iret",
    ],
)
def test_disassembly_reassembles_to_identical_bytes(line):
    bus, _ = load(line)
    ((address, _, text),) = disassemble(bus.peek16, 0x100, 1)
    assert address == 0x100
    assert assemble(text).segments == assemble(line).segments


def test_symbols_replace_addresses():
    source = "start: call helper\njmp start\nhelper: mov r0, byte [r1 + table]\nret\ntable: .db 1"
    bus, symbols = load(source)
    lines = [text for _, _, text in disassemble(bus.peek16, 0x100, 4, label_names(symbols))]
    assert lines == ["call helper", "jmp start", "mov r0, byte [r1 + table]", "ret"]


def test_illegal_words_are_shown_as_data():
    bus, _ = load(".dw 0xFFFF\nhalt")
    lines = list(disassemble(bus.peek16, 0x100, 2))
    assert lines == [(0x100, (0xFFFF,), ".dw 0xFFFF"), (0x102, (0x0400,), "halt")]


def test_global_labels_win_over_local_ones():
    names = label_names({"main.loop": 0x100, "main": 0x100, "zeta": 0x104, "alpha": 0x104})
    assert names == {0x100: "main", 0x104: "alpha"}

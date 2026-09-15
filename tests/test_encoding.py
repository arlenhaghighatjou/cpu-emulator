import pytest

from cpuemulator.decoder import decode, decode_word
from cpuemulator.instructions import BY_NAME, BYTE, OPS, Mode, encode


def test_opcodes_are_unique_and_fit_six_bits():
    codes = [op.code for op in OPS]
    assert len(codes) == len(set(codes))
    assert all(0 <= code < 64 for code in codes)


def test_fields_round_trip_through_the_word():
    word = encode(0x08, Mode.IDX | BYTE, 5, 2)
    decoded = decode_word(word)
    assert decoded is not None
    assert (decoded.op.name, decoded.mode, decoded.rd, decoded.rs) == ("add", 0xC, 5, 2)
    assert decoded.ext == 1


def test_unknown_opcode_is_illegal():
    assert decode_word(0x3F << 10) is None


@pytest.mark.parametrize(
    ("name", "mode", "rd", "rs"),
    [
        ("nop", 0, 1, 0),
        ("mov", 5, 0, 0),
        ("mov", Mode.REG | BYTE, 0, 1),
        ("mov", Mode.IMM, 0, 3),
        ("store", Mode.REG, 1, 2),
        ("store", Mode.ABS, 1, 2),
        ("lea", Mode.REG, 1, 2),
        ("lea", Mode.IND | BYTE, 1, 2),
        ("push", Mode.REG, 1, 2),
        ("not", Mode.IMM, 1, 0),
        ("j", 15, 0, 0),
        ("j", 0, 2, 0),
        ("int", 0, 0, 7),
        ("in", Mode.IND, 0, 0),
    ],
)
def test_malformed_fields_are_illegal(name, mode, rd, rs):
    assert decode_word(encode(BY_NAME[name].code, mode, rd, rs)) is None


@pytest.mark.parametrize(
    ("name", "mode", "rd", "rs", "ext"),
    [
        ("halt", 0, 0, 0, 0),
        ("mov", Mode.REG, 1, 2, 0),
        ("mov", Mode.IMM, 1, 0, 1),
        ("mov", Mode.IND | BYTE, 1, 2, 0),
        ("store", Mode.IDX, 3, 1, 1),
        ("storei", Mode.ABS | BYTE, 0, 0, 2),
        ("storei", Mode.IND, 4, 0, 1),
        ("lea", Mode.IDX, 1, 2, 1),
        ("j", 13, 0, 0, 1),
        ("j", 0, 1, 5, 0),
        ("int", 0, 1, 7, 0),
        ("out", Mode.IMM, 2, 0, 1),
    ],
)
def test_extension_word_counts(name, mode, rd, rs, ext):
    decoded = decode_word(encode(BY_NAME[name].code, mode, rd, rs))
    assert decoded is not None
    assert decoded.ext == ext


def test_cycle_cost_counts_extensions_memory_and_op_cost():
    assert decode_word(encode(BY_NAME["mov"].code, Mode.REG, 1, 2)).cycles == 1
    assert decode_word(encode(BY_NAME["mov"].code, Mode.ABS, 1, 0)).cycles == 3
    assert decode_word(encode(BY_NAME["div"].code, Mode.IMM, 1, 0)).cycles == 10
    assert decode_word(encode(BY_NAME["lea"].code, Mode.IDX, 1, 2)).cycles == 2


def test_decode_reads_operands_little_endian():
    memory = bytearray(16)
    word = encode(BY_NAME["storei"].code, Mode.IDX, 1, 0)
    memory[0:6] = bytes([word & 0xFF, word >> 8, 0x34, 0x12, 0xCD, 0xAB])
    instruction = decode(lambda a: memory[a] | memory[a + 1] << 8, 0)
    assert instruction.operands == (0x1234, 0xABCD)
    assert instruction.size == 6

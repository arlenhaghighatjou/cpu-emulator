from dataclasses import dataclass
from enum import Enum, IntEnum


class Mode(IntEnum):
    REG = 0
    IMM = 1
    IND = 2
    ABS = 3
    IDX = 4


BYTE = 0x8
MEMORY_MODES = (Mode.IND, Mode.ABS, Mode.IDX)


class Form(Enum):
    NONE = "none"
    RD_SRC = "rd, src"
    MEM_RS = "mem, rs"
    MEM_IMM = "mem, imm"
    RD_MEM = "rd, mem"
    RD_RS = "rd, rs"
    RD = "rd"
    SRC = "src"
    JUMP = "target"
    VECTOR = "vector"
    RD_PORT = "rd, port"
    PORT_RD = "port, rd"


@dataclass(frozen=True, slots=True)
class Op:
    code: int
    name: str
    form: Form
    cost: int = 0


OPS = (
    Op(0x00, "nop", Form.NONE),
    Op(0x01, "halt", Form.NONE),
    Op(0x02, "wait", Form.NONE),
    Op(0x03, "mov", Form.RD_SRC),
    Op(0x04, "store", Form.MEM_RS),
    Op(0x05, "storei", Form.MEM_IMM),
    Op(0x06, "lea", Form.RD_MEM),
    Op(0x07, "xchg", Form.RD_RS),
    Op(0x08, "add", Form.RD_SRC),
    Op(0x09, "adc", Form.RD_SRC),
    Op(0x0A, "sub", Form.RD_SRC),
    Op(0x0B, "sbc", Form.RD_SRC),
    Op(0x0C, "mul", Form.RD_SRC, 4),
    Op(0x0D, "div", Form.RD_SRC, 8),
    Op(0x0E, "idiv", Form.RD_SRC, 8),
    Op(0x0F, "mod", Form.RD_SRC, 8),
    Op(0x10, "and", Form.RD_SRC),
    Op(0x11, "or", Form.RD_SRC),
    Op(0x12, "xor", Form.RD_SRC),
    Op(0x13, "not", Form.RD),
    Op(0x14, "neg", Form.RD),
    Op(0x15, "inc", Form.RD),
    Op(0x16, "dec", Form.RD),
    Op(0x17, "shl", Form.RD_SRC),
    Op(0x18, "shr", Form.RD_SRC),
    Op(0x19, "sar", Form.RD_SRC),
    Op(0x1A, "rol", Form.RD_SRC),
    Op(0x1B, "ror", Form.RD_SRC),
    Op(0x1C, "cmp", Form.RD_SRC),
    Op(0x1D, "test", Form.RD_SRC),
    Op(0x1E, "push", Form.SRC),
    Op(0x1F, "pop", Form.RD),
    Op(0x20, "pushf", Form.NONE),
    Op(0x21, "popf", Form.NONE),
    Op(0x22, "j", Form.JUMP),
    Op(0x23, "call", Form.SRC),
    Op(0x24, "ret", Form.NONE),
    Op(0x25, "int", Form.VECTOR),
    Op(0x26, "iret", Form.NONE),
    Op(0x27, "brk", Form.NONE),
    Op(0x28, "cli", Form.NONE),
    Op(0x29, "sti", Form.NONE),
    Op(0x2A, "clc", Form.NONE),
    Op(0x2B, "stc", Form.NONE),
    Op(0x2C, "cmc", Form.NONE),
    Op(0x2D, "in", Form.RD_PORT),
    Op(0x2E, "out", Form.PORT_RD),
)

BY_CODE = {op.code: op for op in OPS}
BY_NAME = {op.name: op for op in OPS}

CONDITIONS = (
    "mp",
    "eq",
    "ne",
    "lo",
    "hs",
    "mi",
    "pl",
    "vs",
    "vc",
    "hi",
    "ls",
    "ge",
    "lt",
    "gt",
    "le",
)
CONDITION_ALIASES = {"z": 1, "nz": 2, "c": 3, "b": 3, "nc": 4, "ae": 4, "a": 9, "be": 10}

JUMP_IMM = 0
JUMP_REG = 1


def encode(code: int, mode: int = 0, rd: int = 0, rs: int = 0) -> int:
    return code << 10 | mode << 6 | rd << 3 | rs


def mode_ext(mode: int) -> int:
    return 0 if mode & 7 in (Mode.REG, Mode.IND) else 1


def jump_condition(mnemonic: str) -> int | None:
    if not mnemonic.startswith("j"):
        return None
    name = mnemonic[1:]
    if name in CONDITIONS:
        return CONDITIONS.index(name)
    return CONDITION_ALIASES.get(name)

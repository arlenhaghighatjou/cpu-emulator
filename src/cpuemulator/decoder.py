from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

from cpuemulator.arch import VEC_SOFT_BASE, VECTOR_COUNT
from cpuemulator.instructions import (
    BY_CODE,
    BYTE,
    CONDITIONS,
    JUMP_IMM,
    JUMP_REG,
    MEMORY_MODES,
    Form,
    Mode,
    Op,
    mode_ext,
)


@dataclass(frozen=True, slots=True)
class Decoded:
    op: Op
    mode: int
    rd: int
    rs: int
    ext: int
    cycles: int


@dataclass(frozen=True, slots=True)
class Instruction:
    address: int
    word: int
    decoded: Decoded
    operands: tuple[int, ...]

    @property
    def size(self) -> int:
        return 2 + 2 * len(self.operands)

    @property
    def op(self) -> Op:
        return self.decoded.op


def _valid_src(mode: int, rd_used: bool, rd: int, rs: int) -> bool:
    kind = mode & 7
    if kind > Mode.IDX:
        return False
    if mode & BYTE and kind not in MEMORY_MODES:
        return False
    if kind in (Mode.IMM, Mode.ABS) and rs:
        return False
    return rd_used or rd == 0


def _valid_mem(mode: int, base: int, other: int) -> bool:
    kind = mode & 7
    if kind not in MEMORY_MODES:
        return False
    if kind == Mode.ABS and base:
        return False
    return other == 0


def _check(op: Op, mode: int, rd: int, rs: int) -> tuple[bool, int]:
    kind = mode & 7
    match op.form:
        case Form.NONE:
            return mode == rd == rs == 0, 0
        case Form.RD_SRC:
            return _valid_src(mode, True, rd, rs), mode_ext(mode)
        case Form.SRC:
            return _valid_src(mode, False, rd, rs), mode_ext(mode)
        case Form.MEM_RS:
            return _valid_mem(mode, rd, 0), mode_ext(mode)
        case Form.MEM_IMM:
            return _valid_mem(mode, rd, rs), mode_ext(mode) + 1
        case Form.RD_MEM:
            valid = kind in MEMORY_MODES and not mode & BYTE
            return valid and _valid_src(mode, True, rd, rs), mode_ext(mode)
        case Form.RD_RS:
            return mode == 0, 0
        case Form.RD:
            return mode == 0 and rs == 0, 0
        case Form.JUMP:
            if mode >= len(CONDITIONS):
                return False, 0
            if rd == JUMP_IMM:
                return rs == 0, 1
            return rd == JUMP_REG, 0
        case Form.VECTOR:
            return mode == 0 and VEC_SOFT_BASE <= (rd << 3 | rs) < VECTOR_COUNT, 0
        case Form.RD_PORT | Form.PORT_RD:
            return mode in (Mode.REG, Mode.IMM) and (mode == Mode.REG or rs == 0), mode_ext(mode)
    return False, 0


@cache
def decode_word(word: int) -> Decoded | None:
    op = BY_CODE.get(word >> 10)
    if op is None:
        return None
    mode = (word >> 6) & 0xF
    rd = (word >> 3) & 7
    rs = word & 7
    valid, ext = _check(op, mode, rd, rs)
    if not valid:
        return None
    memory = op.form not in (Form.JUMP, Form.VECTOR, Form.NONE, Form.RD, Form.RD_RS)
    touches = memory and mode & 7 in MEMORY_MODES and op.form is not Form.RD_MEM
    return Decoded(op, mode, rd, rs, ext, 1 + ext + touches + op.cost)


def decode(read16: Callable[[int], int], address: int) -> Instruction | None:
    word = read16(address)
    decoded = decode_word(word)
    if decoded is None:
        return None
    operands = tuple(read16((address + 2 + 2 * i) & 0xFFFF) for i in range(decoded.ext))
    return Instruction(address, word, decoded, operands)

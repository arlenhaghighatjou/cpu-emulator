from collections.abc import Callable, Iterator

from cpuemulator.decoder import Instruction, decode
from cpuemulator.instructions import BYTE, CONDITIONS, JUMP_IMM, Form, Mode

REGISTER_TEXT = ("r0", "r1", "r2", "r3", "r4", "r5", "fp", "sp")


def _number(value: int) -> str:
    return f"0x{value:04X}" if value > 9 else str(value)


def _address(value: int, names: dict[int, str]) -> str:
    return names.get(value, f"0x{value:04X}")


def _disp(value: int, names: dict[int, str]) -> str:
    if value in names:
        return f"+ {names[value]}"
    if value >= 0xFF00:
        return f"- {0x10000 - value}"
    return f"+ {_number(value)}"


def _memory(mode: int, base: int, operand: int, names: dict[int, str]) -> str:
    prefix = "byte " if mode & BYTE else ""
    match mode & 7:
        case Mode.IND:
            inner = REGISTER_TEXT[base]
        case Mode.ABS:
            inner = _address(operand, names)
        case _:
            inner = f"{REGISTER_TEXT[base]} {_disp(operand, names)}"
    return f"{prefix}[{inner}]"


def _source(mode: int, rs: int, operands: tuple[int, ...], names: dict[int, str]) -> str:
    kind = mode & 7
    if kind == Mode.REG:
        return REGISTER_TEXT[rs]
    if kind == Mode.IMM:
        return _number(operands[0])
    return _memory(mode, rs, operands[0] if operands else 0, names)


def format_instruction(instruction: Instruction, names: dict[int, str] | None = None) -> str:
    names = names or {}
    d = instruction.decoded
    ops = instruction.operands
    name = d.op.name
    rd = REGISTER_TEXT[d.rd]
    match d.op.form:
        case Form.NONE:
            return name
        case Form.RD_SRC | Form.RD_MEM:
            return f"{name} {rd}, {_source(d.mode, d.rs, ops, names)}"
        case Form.SRC:
            target = ops[0] if d.mode & 7 == Mode.IMM and name == "call" else None
            if target is not None:
                return f"call {_address(target, names)}"
            return f"{name} {_source(d.mode, d.rs, ops, names)}"
        case Form.MEM_RS:
            memory = _memory(d.mode, d.rd, ops[0] if ops else 0, names)
            return f"mov {memory}, {REGISTER_TEXT[d.rs]}"
        case Form.MEM_IMM:
            memory = _memory(d.mode, d.rd, ops[0] if len(ops) == 2 else 0, names)
            return f"mov {memory if d.mode & BYTE else 'word ' + memory}, {_number(ops[-1])}"
        case Form.RD_RS:
            return f"{name} {rd}, {REGISTER_TEXT[d.rs]}"
        case Form.RD:
            return f"{name} {rd}"
        case Form.JUMP:
            mnemonic = "j" + CONDITIONS[d.mode]
            if d.rd == JUMP_IMM:
                return f"{mnemonic} {_address(ops[0], names)}"
            return f"{mnemonic} {REGISTER_TEXT[d.rs]}"
        case Form.VECTOR:
            return f"int {d.rd << 3 | d.rs}"
        case Form.RD_PORT:
            port = _number(ops[0]) if d.mode == Mode.IMM else REGISTER_TEXT[d.rs]
            return f"in {rd}, {port}"
        case Form.PORT_RD:
            port = _number(ops[0]) if d.mode == Mode.IMM else REGISTER_TEXT[d.rs]
            return f"out {port}, {rd}"
    raise AssertionError(d.op.form)


def disassemble(
    read16: Callable[[int], int],
    address: int,
    count: int,
    names: dict[int, str] | None = None,
) -> Iterator[tuple[int, tuple[int, ...], str]]:
    for _ in range(count):
        instruction = decode(read16, address)
        if instruction is None:
            word = read16(address)
            yield address, (word,), f".dw 0x{word:04X}"
            address = (address + 2) & 0xFFFF
            continue
        words = (instruction.word, *instruction.operands)
        yield address, words, format_instruction(instruction, names)
        address = (address + instruction.size) & 0xFFFF


def label_names(symbols: dict[str, int]) -> dict[int, str]:
    names: dict[int, str] = {}
    for name, value in sorted(symbols.items(), key=lambda item: ("." in item[0], item[0])):
        names.setdefault(value, name)
    return names

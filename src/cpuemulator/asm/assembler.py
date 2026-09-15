from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cpuemulator.arch import ADDRESS_SPACE, IO_BASE, PROGRAM_BASE
from cpuemulator.asm.lexer import AsmError, Token, tokenize
from cpuemulator.asm.parser import (
    Binary,
    Constant,
    Current,
    Directive,
    Expr,
    Immediate,
    Instruction,
    Label,
    Memory,
    Number,
    Operand,
    Register,
    Statement,
    Symbol,
    Text,
    Unary,
    parse,
)
from cpuemulator.image import Image
from cpuemulator.instructions import (
    BY_NAME,
    BYTE,
    JUMP_IMM,
    JUMP_REG,
    Form,
    Mode,
    encode,
    jump_condition,
)

LIBRARY = Path(__file__).resolve().parent.parent / "programs"


@dataclass(frozen=True, slots=True)
class ListingEntry:
    address: int
    data: bytes
    file: str
    line: int


def _kind(operand: Operand) -> str:
    match operand:
        case Register():
            return "a register"
        case Immediate():
            return "an immediate value"
    return "a memory operand"


class Assembler:
    def __init__(self, include_paths: Sequence[Path] = ()) -> None:
        self.include_paths = [*include_paths, LIBRARY]
        self.statements: list[Statement] = []
        self.labels: dict[str, int] = {}
        self.constants: dict[str, Constant] = {}
        self.sources: dict[str, list[str]] = {}
        self.listing: list[ListingEntry] = []
        self._output = bytearray(ADDRESS_SPACE)
        self._used = bytearray(ADDRESS_SPACE)
        self._files: dict[str, int] = {}
        self._lines: dict[int, tuple[int, int]] = {}
        self._entry: int | None = None
        self._first: int | None = None
        self._final = False
        self._scope = ""

    def assemble_file(self, path: Path) -> Image:
        path = Path(path)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AsmError(f"cannot read {path}: {exc.strerror}", str(path)) from None
        self._read(source, str(path), (str(path.resolve()),))
        return self._build()

    def assemble(self, source: str, file: str = "<source>") -> Image:
        self._read(source, file, ())
        return self._build()

    def listing_text(self) -> str:
        rows = []
        for entry in self.listing:
            text = self.sources[entry.file][entry.line - 1].rstrip()
            for offset in range(0, max(len(entry.data), 1), 6):
                chunk = entry.data[offset : offset + 6].hex(" ").upper()
                address = entry.address + offset
                source = text if offset == 0 else ""
                rows.append(f"{address:04X}  {chunk:<17}  {source}".rstrip())
        return "\n".join(rows)

    def _read(self, source: str, file: str, stack: tuple[str, ...]) -> None:
        self.sources[file] = source.splitlines()
        for statement in parse(tokenize(source, file)):
            if isinstance(statement, Directive) and statement.name == ".include":
                path = self._include(statement, file)
                key = str(path.resolve())
                if key in stack:
                    raise statement.token.error(f"recursive include of {path}")
                self._read(path.read_text(encoding="utf-8"), str(path), (*stack, key))
                continue
            if isinstance(statement, Label) and not statement.name.startswith("."):
                self._scope = statement.name
            statement.scope = self._scope
            self.statements.append(statement)

    def _include(self, directive: Directive, file: str) -> Path:
        if len(directive.args) != 1 or not isinstance(directive.args[0], Text):
            raise directive.token.error(".include takes one quoted path")
        name = directive.args[0].value
        roots = [Path(file).parent] if not file.startswith("<") else [Path.cwd()]
        for root in [*roots, *self.include_paths]:
            candidate = root / name
            if candidate.is_file():
                return candidate
        raise directive.args[0].token.error(f"include file '{name}' not found")

    def _build(self) -> Image:
        self._final = False
        address = PROGRAM_BASE
        for statement in self.statements:
            statement.address = address
            match statement:
                case Label():
                    self._define(statement.token, self._qualify(statement.name, statement.scope))
                    self.labels[self._qualify(statement.name, statement.scope)] = address
                case Constant():
                    self._define(statement.token, statement.name)
                    self.constants[statement.name] = statement
                case Instruction():
                    address += 2 * len(self._encode(statement))
                case Directive():
                    address = self._layout(statement, address)
            if address > ADDRESS_SPACE:
                raise statement.token.error("program runs past the end of memory")
        self._final = True
        for statement in self.statements:
            match statement:
                case Instruction():
                    words = self._encode(statement)
                    self._emit(statement, b"".join(w.to_bytes(2, "little") for w in words))
                case Directive():
                    self._data(statement)
        image = Image(self._entry_point())
        image.segments = self._segments()
        image.symbols = dict(self.labels)
        image.files = list(self._files)
        image.lines = dict(self._lines)
        return image

    def _entry_point(self) -> int:
        if self._entry is not None:
            return self._entry
        return PROGRAM_BASE if self._first is None else self._first

    def _define(self, token: Token, name: str) -> None:
        if name in self.labels or name in self.constants:
            raise token.error(f"'{name}' is already defined")

    def _qualify(self, name: str, scope: str) -> str:
        return scope + name if name.startswith(".") else name

    def _eval(self, expr: Expr, statement: Statement, stack: tuple[str, ...] = ()) -> int:
        match expr:
            case Number():
                return expr.value
            case Current():
                return statement.address
            case Symbol():
                name = self._qualify(expr.name, statement.scope)
                if name in self.labels:
                    return self.labels[name]
                if name in self.constants:
                    if name in stack:
                        raise expr.token.error(f"constant '{name}' refers to itself")
                    constant = self.constants[name]
                    return self._eval(constant.expr, constant, (*stack, name))
                if self._final:
                    raise expr.token.error(f"undefined symbol '{expr.name}'")
                raise expr.token.error(f"'{expr.name}' must be defined before it is used here")
            case Unary():
                value = self._eval(expr.operand, statement, stack)
                return {"-": -value, "+": value, "~": ~value}[expr.op]
            case Binary():
                left = self._eval(expr.left, statement, stack)
                right = self._eval(expr.right, statement, stack)
                return self._binary(expr, left, right)
        raise TypeError(expr)

    def _binary(self, expr: Binary, left: int, right: int) -> int:
        match expr.op:
            case "+":
                return left + right
            case "-":
                return left - right
            case "*":
                return left * right
            case "/" | "%":
                if right == 0:
                    raise expr.token.error("division by zero in expression")
                quotient = abs(left) // abs(right)
                if (left < 0) != (right < 0):
                    quotient = -quotient
                return quotient if expr.op == "/" else left - quotient * right
            case "&":
                return left & right
            case "|":
                return left | right
            case "^":
                return left ^ right
        if right < 0:
            raise expr.token.error("negative shift count")
        return left << right if expr.op == "<<" else left >> right

    def _value(self, expr: Expr, statement: Statement) -> int:
        if not self._final:
            return 0
        return self._eval(expr, statement)

    def _word(self, value: int, token: Token) -> int:
        if not -0x8000 <= value <= 0xFFFF:
            raise token.error(f"value {value} does not fit in 16 bits")
        return value & 0xFFFF

    def _byte(self, value: int, token: Token) -> int:
        if not -0x80 <= value <= 0xFF:
            raise token.error(f"value {value} does not fit in a byte")
        return value & 0xFF

    def _memory(self, operand: Memory, statement: Statement) -> tuple[int, int, list[int]]:
        width = BYTE if operand.width == "byte" else 0
        if operand.base is None:
            disp = self._value(operand.disp, statement)
            return Mode.ABS | width, 0, [self._word(disp, operand.token)]
        if operand.disp is None:
            return Mode.IND | width, operand.base, []
        disp = self._value(operand.disp, statement)
        return Mode.IDX | width, operand.base, [self._word(disp, operand.token)]

    def _source(self, operand: Operand, statement: Statement) -> tuple[int, int, list[int]]:
        match operand:
            case Register():
                return Mode.REG, operand.index, []
            case Immediate():
                return (
                    Mode.IMM,
                    0,
                    [self._word(self._value(operand.expr, statement), operand.token)],
                )
        return self._memory(operand, statement)

    def _port(self, operand: Operand, statement: Instruction) -> tuple[int, int, list[int]]:
        match operand:
            case Register():
                return Mode.REG, operand.index, []
            case Immediate():
                port = self._value(operand.expr, statement)
                if not 0 <= port <= 0xFF:
                    raise operand.token.error(f"port {port} is outside 0-255")
                return Mode.IMM, 0, [port]
        raise operand.token.error(f"'{statement.mnemonic}' port must be a register or immediate")

    def _expect(self, statement: Instruction, count: int) -> None:
        if len(statement.operands) != count:
            plural = "operand" if count == 1 else "operands"
            raise statement.token.error(
                f"'{statement.mnemonic}' takes {count} {plural}, got {len(statement.operands)}"
            )

    def _register(self, operand: Operand, statement: Instruction, role: str) -> int:
        if not isinstance(operand, Register):
            raise operand.token.error(
                f"{role} of '{statement.mnemonic}' must be a register, not {_kind(operand)}"
            )
        return operand.index

    def _encode(self, statement: Instruction) -> list[int]:
        mnemonic = statement.mnemonic
        operands = statement.operands
        condition = jump_condition(mnemonic)
        if condition is not None:
            self._expect(statement, 1)
            op = BY_NAME["j"]
            target = operands[0]
            match target:
                case Register():
                    return [encode(op.code, condition, JUMP_REG, target.index)]
                case Immediate():
                    value = self._word(self._value(target.expr, statement), target.token)
                    return [encode(op.code, condition, JUMP_IMM, 0), value]
            raise target.token.error("jump target must be an address or a register")
        op = BY_NAME.get(mnemonic)
        if op is None or op.form is Form.JUMP:
            raise statement.token.error(f"unknown instruction '{mnemonic}'")
        if mnemonic == "mov" and len(operands) == 2 and isinstance(operands[0], Memory):
            op = BY_NAME["storei" if isinstance(operands[1], Immediate) else "store"]
        match op.form:
            case Form.NONE:
                self._expect(statement, 0)
                return [encode(op.code)]
            case Form.RD_SRC:
                self._expect(statement, 2)
                rd = self._register(operands[0], statement, "destination")
                mode, rs, ext = self._source(operands[1], statement)
                return [encode(op.code, mode, rd, rs), *ext]
            case Form.SRC:
                self._expect(statement, 1)
                mode, rs, ext = self._source(operands[0], statement)
                return [encode(op.code, mode, 0, rs), *ext]
            case Form.MEM_RS | Form.MEM_IMM:
                return self._store(op.code, op.form, statement)
            case Form.RD_MEM:
                self._expect(statement, 2)
                rd = self._register(operands[0], statement, "destination")
                address = operands[1]
                if not isinstance(address, Memory) or address.width:
                    raise address.token.error("lea needs an unsized memory operand")
                mode, rs, ext = self._memory(address, statement)
                return [encode(op.code, mode, rd, rs), *ext]
            case Form.RD_RS:
                self._expect(statement, 2)
                rd = self._register(operands[0], statement, "first operand")
                rs = self._register(operands[1], statement, "second operand")
                return [encode(op.code, 0, rd, rs)]
            case Form.RD:
                self._expect(statement, 1)
                return [encode(op.code, 0, self._register(operands[0], statement, "operand"))]
            case Form.VECTOR:
                self._expect(statement, 1)
                vector = operands[0]
                if not isinstance(vector, Immediate):
                    raise vector.token.error("int needs a constant vector number")
                number = self._value(vector.expr, statement) if self._final else 8
                if not 8 <= number <= 31:
                    raise vector.token.error(f"software interrupt vector {number} is outside 8-31")
                return [encode(op.code, 0, number >> 3, number & 7)]
            case Form.RD_PORT:
                self._expect(statement, 2)
                rd = self._register(operands[0], statement, "destination")
                mode, rs, ext = self._port(operands[1], statement)
                return [encode(op.code, mode, rd, rs), *ext]
            case Form.PORT_RD:
                self._expect(statement, 2)
                mode, rs, ext = self._port(operands[0], statement)
                rd = self._register(operands[1], statement, "value")
                return [encode(op.code, mode, rd, rs), *ext]
        raise AssertionError(op.form)

    def _store(self, code: int, form: Form, statement: Instruction) -> list[int]:
        self._expect(statement, 2)
        target, value = statement.operands
        if not isinstance(target, Memory):
            raise target.token.error("store destination must be a memory operand")
        mode, base, ext = self._memory(target, statement)
        if form is Form.MEM_RS:
            if not isinstance(value, Register):
                raise value.token.error("cannot move memory to memory, load it into a register")
            return [encode(code, mode, base, value.index), *ext]
        if not isinstance(value, Immediate):
            raise value.token.error("storei needs an immediate value")
        number = self._value(value.expr, statement)
        fit = self._byte if mode & BYTE else self._word
        return [encode(code, mode, base, 0), *ext, fit(number, value.token)]

    def _layout(self, directive: Directive, address: int) -> int:
        args = directive.args
        match directive.name:
            case ".org":
                self._count(directive, 1)
                target = self._eval(self._expr(args[0]), directive)
                if not 0 <= target < ADDRESS_SPACE:
                    raise directive.token.error(f"origin {target} is outside the address space")
                return target
            case ".equ":
                self._count(directive, 2)
                name = args[0]
                if not isinstance(name, Symbol) or name.name.startswith("."):
                    raise directive.token.error(".equ needs a constant name first")
                self._define(name.token, name.name)
                self.constants[name.name] = Constant(
                    name.name, self._expr(args[1]), name.token, directive.scope, address
                )
                return address
            case ".entry":
                self._count(directive, 1)
                return address
            case ".db" | ".ascii" | ".asciz" | ".dw":
                return address + len(self._bytes(directive))
            case ".ds":
                if len(args) not in (1, 2):
                    raise directive.token.error(".ds takes a size and an optional fill byte")
                size = self._eval(self._expr(args[0]), directive)
                if size < 0:
                    raise directive.token.error(f"negative .ds size {size}")
                return address + size
            case ".align":
                self._count(directive, 1)
                step = self._eval(self._expr(args[0]), directive)
                if step <= 0:
                    raise directive.token.error(".align needs a positive size")
                return (address + step - 1) // step * step
        raise directive.token.error(f"unknown directive '{directive.name}'")

    def _data(self, directive: Directive) -> None:
        match directive.name:
            case ".entry":
                value = self._eval(self._expr(directive.args[0]), directive)
                self._entry = self._word(value, directive.token)
            case ".db" | ".ascii" | ".asciz" | ".dw":
                self._emit(directive, self._bytes(directive))
            case ".ds":
                size = self._eval(self._expr(directive.args[0]), directive)
                fill = 0
                if len(directive.args) == 2:
                    fill = self._eval(self._expr(directive.args[1]), directive)
                    fill = self._byte(fill, directive.token)
                self._emit(directive, bytes([fill]) * size)

    def _bytes(self, directive: Directive) -> bytes:
        out = bytearray()
        name = directive.name
        if name in (".ascii", ".asciz") and not all(isinstance(a, Text) for a in directive.args):
            raise directive.token.error(f"{name} takes quoted strings")
        if not directive.args:
            raise directive.token.error(f"{name} needs at least one value")
        for arg in directive.args:
            if isinstance(arg, Text):
                try:
                    encoded = arg.value.encode("latin-1")
                except UnicodeEncodeError:
                    raise arg.token.error("strings must be 8-bit characters") from None
                if name == ".dw":
                    for char in encoded:
                        out += char.to_bytes(2, "little")
                else:
                    out += encoded
                continue
            value = self._value(arg, directive)
            if name == ".dw":
                out += self._word(value, arg.token).to_bytes(2, "little")
            else:
                out.append(self._byte(value, arg.token))
        if name == ".asciz":
            out.append(0)
        return bytes(out)

    def _expr(self, arg: Expr | Text) -> Expr:
        if isinstance(arg, Text):
            raise arg.token.error("expected an expression, found a string")
        return arg

    def _count(self, directive: Directive, count: int) -> None:
        if len(directive.args) != count:
            raise directive.token.error(f"{directive.name} takes {count} argument(s)")

    def _emit(self, statement: Statement, data: bytes) -> None:
        address = statement.address
        end = address + len(data)
        if end > IO_BASE:
            raise statement.token.error(f"code at {address:04X} runs into the I/O page")
        if any(self._used[address:end]):
            raise statement.token.error(f"bytes at {address:04X} overlap earlier output")
        self._output[address:end] = data
        self._used[address:end] = b"\x01" * len(data)
        token = statement.token
        file = self._files.setdefault(token.file, len(self._files))
        self._lines[address] = (file, token.line)
        self.listing.append(ListingEntry(address, data, token.file, token.line))
        if self._first is None and data:
            self._first = address

    def _segments(self) -> list[tuple[int, bytes]]:
        segments = []
        start = self._used.find(1)
        while start != -1:
            end = self._used.find(0, start)
            if end == -1:
                end = ADDRESS_SPACE
            segments.append((start, bytes(self._output[start:end])))
            start = self._used.find(1, end)
        return segments


def assemble(source: str, file: str = "<source>", include_paths: Sequence[Path] = ()) -> Image:
    return Assembler(include_paths).assemble(source, file)


def assemble_file(path: Path, include_paths: Sequence[Path] = ()) -> Image:
    return Assembler(include_paths).assemble_file(path)

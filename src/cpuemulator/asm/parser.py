from dataclasses import dataclass

from cpuemulator.arch import REGISTER_ALIASES, REGISTERS
from cpuemulator.asm.lexer import Kind, Token

REGISTER_NAMES = {name: index for index, name in enumerate(REGISTERS)} | REGISTER_ALIASES
BINARY_LEVELS = (("|",), ("^",), ("&",), ("<<", ">>"), ("+", "-"), ("*", "/", "%"))
TERM_LEVEL = len(BINARY_LEVELS) - 1
WIDTHS = ("byte", "word")


@dataclass(frozen=True, slots=True)
class Number:
    value: int
    token: Token


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    token: Token


@dataclass(frozen=True, slots=True)
class Current:
    token: Token


@dataclass(frozen=True, slots=True)
class Unary:
    op: str
    operand: "Expr"
    token: Token


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    token: Token


type Expr = Number | Symbol | Current | Unary | Binary


@dataclass(frozen=True, slots=True)
class Text:
    value: str
    token: Token


@dataclass(frozen=True, slots=True)
class Register:
    index: int
    token: Token


@dataclass(frozen=True, slots=True)
class Immediate:
    expr: Expr
    token: Token


@dataclass(frozen=True, slots=True)
class Memory:
    base: int | None
    disp: Expr | None
    width: str | None
    token: Token


type Operand = Register | Immediate | Memory


@dataclass(slots=True)
class Label:
    name: str
    token: Token
    scope: str = ""
    address: int = 0


@dataclass(slots=True)
class Constant:
    name: str
    expr: Expr
    token: Token
    scope: str = ""
    address: int = 0


@dataclass(slots=True)
class Instruction:
    mnemonic: str
    operands: list[Operand]
    token: Token
    scope: str = ""
    address: int = 0


@dataclass(slots=True)
class Directive:
    name: str
    args: list[Expr | Text]
    token: Token
    scope: str = ""
    address: int = 0


type Statement = Label | Constant | Instruction | Directive


def describe(token: Token) -> str:
    if token.kind in (Kind.NEWLINE, Kind.EOF):
        return token.kind.value
    return f"'{token.text}'"


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self, ahead: int = 0) -> Token:
        return self.tokens[min(self.pos + ahead, len(self.tokens) - 1)]

    def advance(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def at(self, text: str, ahead: int = 0) -> bool:
        token = self.peek(ahead)
        return token.kind is Kind.PUNCT and token.text == text

    def expect(self, text: str) -> Token:
        if not self.at(text):
            raise self.peek().error(f"expected '{text}', found {describe(self.peek())}")
        return self.advance()

    def parse(self) -> list[Statement]:
        statements: list[Statement] = []
        while self.peek().kind is not Kind.EOF:
            if self.peek().kind is Kind.NEWLINE:
                self.advance()
                continue
            statements.extend(self.line())
        return statements

    def line(self) -> list[Statement]:
        statements: list[Statement] = []
        token = self.peek()
        if token.kind in (Kind.IDENT, Kind.DOTNAME) and self.at(":", 1):
            self.advance()
            self.advance()
            statements.append(Label(token.text, token))
            token = self.peek()
        if token.kind is Kind.NEWLINE:
            return statements
        if token.kind is Kind.IDENT and self.at("=", 1):
            self.advance()
            self.advance()
            statements.append(Constant(token.text, self.expr(), token))
        elif token.kind is Kind.DOTNAME:
            self.advance()
            statements.append(Directive(token.text.lower(), self.arguments(), token))
        elif token.kind is Kind.IDENT:
            self.advance()
            statements.append(Instruction(token.text.lower(), self.operands(), token))
        else:
            raise token.error(
                f"expected a label, directive or instruction, found {describe(token)}"
            )
        if self.peek().kind is not Kind.NEWLINE:
            raise self.peek().error(f"expected end of line, found {describe(self.peek())}")
        return statements

    def arguments(self) -> list[Expr | Text]:
        args: list[Expr | Text] = []
        if self.peek().kind is Kind.NEWLINE:
            return args
        while True:
            token = self.peek()
            if token.kind is Kind.STRING:
                self.advance()
                args.append(Text(str(token.value), token))
            else:
                args.append(self.expr())
            if not self.at(","):
                return args
            self.advance()

    def operands(self) -> list[Operand]:
        operands: list[Operand] = []
        if self.peek().kind is Kind.NEWLINE:
            return operands
        while True:
            operands.append(self.operand())
            if not self.at(","):
                return operands
            self.advance()

    def operand(self) -> Operand:
        token = self.peek()
        width = None
        if token.kind is Kind.IDENT and token.text.lower() in WIDTHS and self.at("[", 1):
            width = token.text.lower()
            self.advance()
        if self.at("["):
            return self.memory(token, width)
        if token.kind is Kind.IDENT and token.text.lower() in REGISTER_NAMES:
            self.advance()
            return Register(REGISTER_NAMES[token.text.lower()], token)
        return Immediate(self.expr(), token)

    def memory(self, start: Token, width: str | None) -> Memory:
        self.expect("[")
        base = None
        disp: Expr | None = None
        while True:
            sign = "+"
            if self.at("+") or self.at("-"):
                sign = self.advance().text
            token = self.peek()
            if token.kind is Kind.IDENT and token.text.lower() in REGISTER_NAMES:
                if base is not None or sign == "-":
                    raise token.error("a memory operand can only add one register")
                base = REGISTER_NAMES[token.text.lower()]
                self.advance()
            else:
                term = self.expr(TERM_LEVEL)
                if sign == "-":
                    term = Unary("-", term, token)
                disp = term if disp is None else Binary("+", disp, term, token)
            if not (self.at("+") or self.at("-")):
                break
        self.expect("]")
        return Memory(base, disp, width, start)

    def expr(self, level: int = 0) -> Expr:
        if level == len(BINARY_LEVELS):
            return self.unary()
        left = self.expr(level + 1)
        while self.peek().kind is Kind.PUNCT and self.peek().text in BINARY_LEVELS[level]:
            token = self.advance()
            left = Binary(token.text, left, self.expr(level + 1), token)
        return left

    def unary(self) -> Expr:
        token = self.peek()
        if token.kind is Kind.PUNCT and token.text in ("-", "~", "+"):
            self.advance()
            return Unary(token.text, self.unary(), token)
        return self.primary()

    def primary(self) -> Expr:
        token = self.advance()
        match token.kind:
            case Kind.NUMBER:
                return Number(int(token.value), token)
            case Kind.IDENT:
                if token.text.lower() in REGISTER_NAMES:
                    raise token.error(f"register '{token.text}' cannot be used in an expression")
                return Symbol(token.text, token)
            case Kind.DOTNAME:
                return Symbol(token.text, token)
            case Kind.PUNCT if token.text == "$":
                return Current(token)
            case Kind.PUNCT if token.text == "(":
                inner = self.expr()
                self.expect(")")
                return inner
        raise token.error(f"expected an expression, found {describe(token)}")


def parse(tokens: list[Token]) -> list[Statement]:
    return Parser(tokens).parse()

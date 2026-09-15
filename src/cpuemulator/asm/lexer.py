from dataclasses import dataclass
from enum import Enum


class AsmError(Exception):
    def __init__(self, message: str, file: str = "<source>", line: int = 0, col: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.file = file
        self.line = line
        self.col = col

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}: {self.message}"


class Kind(Enum):
    IDENT = "identifier"
    DOTNAME = "directive or local label"
    NUMBER = "number"
    STRING = "string"
    PUNCT = "symbol"
    NEWLINE = "end of line"
    EOF = "end of file"


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str
    value: int | str | None
    file: str
    line: int
    col: int

    def error(self, message: str) -> AsmError:
        return AsmError(message, self.file, self.line, self.col)


PUNCTUATION = (
    "<<",
    ">>",
    ",",
    "[",
    "]",
    "(",
    ")",
    "+",
    "-",
    "*",
    "/",
    "%",
    "&",
    "|",
    "^",
    "~",
    ":",
    "=",
    "$",
)
ESCAPES = {"n": 10, "r": 13, "t": 9, "0": 0, "\\": 92, "'": 39, '"': 34, "e": 27}


def _is_name_start(char: str) -> bool:
    return char.isascii() and (char.isalpha() or char == "_")


def _is_name_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


class _Scanner:
    def __init__(self, source: str, file: str) -> None:
        self.source = source
        self.file = file
        self.pos = 0
        self.line = 1
        self.line_start = 0
        self.tokens: list[Token] = []

    @property
    def col(self) -> int:
        return self.pos - self.line_start + 1

    def error(self, message: str, col: int | None = None) -> AsmError:
        return AsmError(message, self.file, self.line, self.col if col is None else col)

    def emit(self, kind: Kind, text: str, value: int | str | None, col: int) -> None:
        self.tokens.append(Token(kind, text, value, self.file, self.line, col))

    def _dotted(self, pos: int) -> bool:
        source = self.source
        return source[pos] == "." and pos + 1 < len(source) and _is_name_start(source[pos + 1])

    def _name_end(self, pos: int) -> int:
        source = self.source
        while pos < len(source):
            if _is_name_char(source[pos]) or self._dotted(pos):
                pos += 1
            else:
                break
        return pos

    def scan(self) -> list[Token]:
        source = self.source
        while self.pos < len(source):
            char = source[self.pos]
            col = self.col
            if char == "\n":
                self.emit(Kind.NEWLINE, "\n", None, col)
                self.pos += 1
                self.line += 1
                self.line_start = self.pos
            elif char in " \t\r":
                self.pos += 1
            elif char == ";":
                while self.pos < len(source) and source[self.pos] != "\n":
                    self.pos += 1
            elif char.isdigit():
                self.number(col)
            elif _is_name_start(char):
                start = self.pos
                self.pos = self._name_end(self.pos)
                name = source[start : self.pos]
                self.emit(Kind.IDENT, name, name, col)
            elif self._dotted(self.pos):
                start = self.pos
                self.pos = self._name_end(self.pos + 1)
                name = source[start : self.pos]
                self.emit(Kind.DOTNAME, name, name, col)
            elif char == '"':
                text = self.quoted('"')
                self.emit(Kind.STRING, text, text, col)
            elif char == "'":
                text = self.quoted("'")
                if len(text) != 1:
                    raise self.error("character literal must hold exactly one character", col)
                self.emit(Kind.NUMBER, text, ord(text), col)
            else:
                self.punct(col)
        self.emit(Kind.NEWLINE, "\n", None, self.col)
        self.emit(Kind.EOF, "", None, self.col)
        return self.tokens

    def number(self, col: int) -> None:
        source = self.source
        start = self.pos
        while self.pos < len(source) and _is_name_char(source[self.pos]):
            self.pos += 1
        text = source[start : self.pos]
        digits = text.replace("_", "").lower()
        base = 10
        if digits.startswith(("0x", "0b", "0o")):
            base = {"x": 16, "b": 2, "o": 8}[digits[1]]
            digits = digits[2:]
        try:
            value = int(digits, base)
        except ValueError:
            raise self.error(f"invalid number '{text}'", col) from None
        self.emit(Kind.NUMBER, text, value, col)

    def quoted(self, quote: str) -> str:
        source = self.source
        col = self.col
        self.pos += 1
        chars = []
        while True:
            if self.pos >= len(source) or source[self.pos] == "\n":
                raise self.error("unterminated string", col)
            char = source[self.pos]
            if char == quote:
                self.pos += 1
                return "".join(chars)
            if char == "\\":
                chars.append(chr(self.escape()))
                continue
            chars.append(char)
            self.pos += 1

    def escape(self) -> int:
        source = self.source
        col = self.col
        if self.pos + 1 >= len(source):
            raise self.error("unterminated escape", col)
        code = source[self.pos + 1]
        if code == "x":
            digits = source[self.pos + 2 : self.pos + 4]
            try:
                value = int(digits, 16)
            except ValueError:
                raise self.error(f"invalid hex escape '\\x{digits}'", col) from None
            self.pos += 4
            return value
        if code not in ESCAPES:
            raise self.error(f"unknown escape '\\{code}'", col)
        self.pos += 2
        return ESCAPES[code]

    def punct(self, col: int) -> None:
        for symbol in PUNCTUATION:
            if self.source.startswith(symbol, self.pos):
                self.pos += len(symbol)
                self.emit(Kind.PUNCT, symbol, symbol, col)
                return
        raise self.error(f"unexpected character '{self.source[self.pos]}'", col)


def tokenize(source: str, file: str = "<source>") -> list[Token]:
    return _Scanner(source, file).scan()

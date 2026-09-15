import pytest

from cpuemulator.asm.lexer import AsmError, Kind, tokenize


def kinds_and_values(source: str) -> list[tuple[Kind, object]]:
    return [(t.kind, t.value) for t in tokenize(source) if t.kind not in (Kind.NEWLINE, Kind.EOF)]


@pytest.mark.parametrize(
    ("text", "value"),
    [("42", 42), ("0x2A", 42), ("0b101010", 42), ("0o52", 42), ("1_000", 1000), ("'*'", 42)],
)
def test_number_literals(text, value):
    assert kinds_and_values(text) == [(Kind.NUMBER, value)]


def test_identifiers_directives_and_punctuation():
    tokens = kinds_and_values(".org 0x100\nstart: mov r0, [r1 + 2] << 1")
    assert tokens == [
        (Kind.DOTNAME, ".org"),
        (Kind.NUMBER, 0x100),
        (Kind.IDENT, "start"),
        (Kind.PUNCT, ":"),
        (Kind.IDENT, "mov"),
        (Kind.IDENT, "r0"),
        (Kind.PUNCT, ","),
        (Kind.PUNCT, "["),
        (Kind.IDENT, "r1"),
        (Kind.PUNCT, "+"),
        (Kind.NUMBER, 2),
        (Kind.PUNCT, "]"),
        (Kind.PUNCT, "<<"),
        (Kind.NUMBER, 1),
    ]


def test_qualified_names_are_single_identifiers():
    assert kinds_and_values("jmp main.loop") == [(Kind.IDENT, "jmp"), (Kind.IDENT, "main.loop")]


def test_comments_are_skipped():
    assert kinds_and_values("nop ; mov r0, 1") == [(Kind.IDENT, "nop")]


def test_string_escapes():
    assert kinds_and_values(r'"a\tb\n\x41\\\"" ') == [(Kind.STRING, 'a\tb\nA\\"')]


def test_positions_are_one_based():
    tokens = tokenize("nop\n  halt")
    halt = tokens[2]
    assert (halt.text, halt.line, halt.col) == ("halt", 2, 3)


@pytest.mark.parametrize(
    ("source", "message", "col"),
    [
        ('mov r0, "abc', "unterminated string", 9),
        ("mov r0, 0x", "invalid number '0x'", 9),
        ("db '\\q'", "unknown escape '\\q'", 5),
        ("mov r0, 'ab'", "character literal must hold exactly one character", 9),
        ("mov r0, @", "unexpected character '@'", 9),
    ],
)
def test_errors_report_location(source, message, col):
    with pytest.raises(AsmError) as info:
        tokenize(source, "game.asm")
    assert info.value.message == message
    assert str(info.value) == f"game.asm:1:{col}: {message}"

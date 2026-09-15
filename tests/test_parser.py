import pytest

from cpuemulator.asm.lexer import AsmError, tokenize
from cpuemulator.asm.parser import (
    Binary,
    Constant,
    Current,
    Directive,
    Immediate,
    Instruction,
    Label,
    Memory,
    Number,
    Register,
    Symbol,
    Text,
    Unary,
    parse,
)


def statements(source: str):
    return parse(tokenize(source))


def test_label_and_instruction_share_a_line():
    label, instruction = statements("start: MOV r0, sp")
    assert isinstance(label, Label)
    assert label.name == "start"
    assert isinstance(instruction, Instruction)
    assert instruction.mnemonic == "mov"
    assert [op.index for op in instruction.operands] == [0, 7]


def test_label_alone_on_a_line():
    (label,) = statements(".loop:\n")
    assert isinstance(label, Label)
    assert label.name == ".loop"


def test_constant_definition():
    (constant,) = statements("WIDTH = 80 * 2")
    assert isinstance(constant, Constant)
    assert isinstance(constant.expr, Binary)


def test_expression_precedence():
    (constant,) = statements("X = 1 + 2 * 3 << 1 | 4")
    expr = constant.expr
    assert expr.op == "|"
    assert expr.left.op == "<<"
    assert expr.left.left.op == "+"
    assert expr.left.left.right.op == "*"


def test_unary_parentheses_and_current_address():
    (instruction,) = statements("jmp -($ + ~1)")
    target = instruction.operands[0]
    assert isinstance(target, Immediate)
    assert isinstance(target.expr, Unary)
    inner = target.expr.operand
    assert isinstance(inner.left, Current)
    assert isinstance(inner.right, Unary)


@pytest.mark.parametrize(
    ("source", "base", "has_disp", "width"),
    [
        ("mov r0, [r1]", 1, False, None),
        ("mov r0, [0x4000]", None, True, None),
        ("mov r0, byte [board + r2]", 2, True, "byte"),
        ("mov r0, word [fp - 4]", 6, True, "word"),
        ("mov r0, [r3 + ROW * 3 + 1]", 3, True, None),
    ],
)
def test_memory_operands(source, base, has_disp, width):
    (instruction,) = statements(source)
    memory = instruction.operands[1]
    assert isinstance(memory, Memory)
    assert memory.base == base
    assert (memory.disp is not None) == has_disp
    assert memory.width == width


def test_negative_displacement_is_negated():
    (instruction,) = statements("lea r0, [fp - 4]")
    disp = instruction.operands[1].disp
    assert isinstance(disp, Unary)
    assert disp.op == "-"
    assert isinstance(disp.operand, Number)


def test_directive_arguments_mix_strings_and_expressions():
    (directive,) = statements('.db "hi", 10, END - START')
    assert isinstance(directive, Directive)
    assert directive.name == ".db"
    assert isinstance(directive.args[0], Text)
    assert isinstance(directive.args[1], Number)
    assert isinstance(directive.args[2], Binary)


def test_register_operand_versus_symbol():
    (instruction,) = statements("push rx")
    assert isinstance(instruction.operands[0], Immediate)
    assert isinstance(instruction.operands[0].expr, Symbol)
    (instruction,) = statements("push R5")
    assert isinstance(instruction.operands[0], Register)


@pytest.mark.parametrize(
    ("source", "message", "col"),
    [
        ("mov r0, [r1 + r2]", "a memory operand can only add one register", 15),
        ("mov r0, [4 - r2]", "a memory operand can only add one register", 14),
        ("mov r0, r1 + 1", "expected end of line, found '+'", 12),
        ("mov r0, [r1", "expected ']', found end of line", 12),
        ("X = r1 + 1", "register 'r1' cannot be used in an expression", 5),
        ("42", "expected a label, directive or instruction, found '42'", 1),
        ("mov r0,", "expected an expression, found end of line", 8),
    ],
)
def test_syntax_errors(source, message, col):
    with pytest.raises(AsmError) as info:
        statements(source)
    assert info.value.message == message
    assert info.value.col == col

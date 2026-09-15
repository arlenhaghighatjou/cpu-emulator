import pytest

from cpuemulator.arch import FLAG_C, FLAG_I, FLAG_N, FLAG_V, FLAG_Z, STACK_TOP
from cpuemulator.asm import assemble
from cpuemulator.cpu import CPU
from cpuemulator.instructions import CONDITIONS
from cpuemulator.machine import Machine


def execute(source: str, budget: int = 200_000) -> Machine:
    machine = Machine(seed=3)
    machine.load(assemble(f'.include "lib/hw.inc"\n{source}\nhalt\n'))
    machine.run(budget)
    return machine


def cpu_after(source: str) -> CPU:
    machine = execute(source)
    assert machine.cpu.halted
    assert machine.cpu.fault is None
    return machine.cpu


def flags_of(source: str) -> int:
    return cpu_after(source).flags & ~FLAG_I


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("mov r0, 0x1234", 0x1234),
        ("mov r1, 7\nmov r0, r1", 7),
        ("mov r1, cell\nmov r0, [r1]\nhalt\n.org 0x3000\ncell: .dw 0xBEEF", 0xBEEF),
        ("mov r0, [0x3000]\nhalt\n.org 0x3000\n.dw 0xCAFE", 0xCAFE),
        ("mov r1, 0x2FFE\nmov r0, [r1 + 2]\nhalt\n.org 0x3000\n.dw 0x0102", 0x0102),
        ("mov r0, byte [0x3001]\nhalt\n.org 0x3000\n.dw 0xAB12", 0xAB),
        ("mov r1, 0xFFFF\nmov r0, byte [r1 + 0x3001]\nhalt\n.org 0x3000\n.db 0x5A", 0x5A),
        ("lea r0, [sp - 6]", STACK_TOP - 6),
        ("mov r1, 0x40\nlea r0, [r1 + 0x40]", 0x80),
        ("mov r0, 1\nmov r1, 2\nxchg r0, r1", 2),
    ],
)
def test_loads_moves_and_addressing(source, expected):
    assert cpu_after(source).reg[0] == expected


def test_store_word_byte_and_immediate():
    machine = execute(
        """
        mov r0, 0x1234
        mov r1, 0x4000
        mov [r1], r0
        mov byte [r1 + 2], r0
        mov [0x4004], r0
        mov word [0x4006], 0xBEEF
        mov byte [r1 + 8], 0x7F
        """
    )
    ram = machine.bus.ram
    assert bytes(ram[0x4000:0x400A]) == bytes(
        [0x34, 0x12, 0x34, 0, 0x34, 0x12, 0xEF, 0xBE, 0x7F, 0]
    )


@pytest.mark.parametrize(
    ("source", "result", "flags"),
    [
        ("mov r0, 2\nadd r0, 3", 5, 0),
        ("mov r0, 0xFFFF\nadd r0, 1", 0, FLAG_C | FLAG_Z),
        ("mov r0, 0x7FFF\nadd r0, 1", 0x8000, FLAG_N | FLAG_V),
        ("mov r0, 0x8000\nadd r0, 0x8000", 0, FLAG_C | FLAG_Z | FLAG_V),
        ("mov r0, 1\nstc\nadc r0, 1", 3, 0),
        ("mov r0, 0xFFFF\nstc\nadc r0, 0", 0, FLAG_C | FLAG_Z),
        ("mov r0, 5\nsub r0, 5", 0, FLAG_Z),
        ("mov r0, 3\nsub r0, 5", 0xFFFE, FLAG_C | FLAG_N),
        ("mov r0, 0x8000\nsub r0, 1", 0x7FFF, FLAG_V),
        ("mov r0, 5\nstc\nsbc r0, 2", 2, 0),
        ("mov r0, 0\nstc\nsbc r0, 0", 0xFFFF, FLAG_C | FLAG_N),
        ("mov r0, 300\nmul r0, 200", 60000, FLAG_N),
        ("mov r0, 0x100\nmul r0, 0x100", 0, FLAG_C | FLAG_V | FLAG_Z),
        ("mov r0, 100\ndiv r0, 7", 14, 0),
        ("mov r0, 0xFFFF\ndiv r0, 0xFFFF", 1, 0),
        ("mov r0, 100\nmod r0, 7", 2, 0),
        ("mov r0, -100\nidiv r0, -7", 14, 0),
        ("mov r0, 100\nidiv r0, -7", (-14) & 0xFFFF, FLAG_N),
        ("mov r0, 0x8000\nidiv r0, -1", 0x8000, FLAG_N | FLAG_V),
        ("mov r0, 0xF0F0\nand r0, 0x0FF0", 0x00F0, 0),
        ("mov r0, 0xF000\nor r0, 0x000F", 0xF00F, FLAG_N),
        ("mov r0, 0xFFFF\nxor r0, 0xFFFF", 0, FLAG_Z),
        ("mov r0, 0x00FF\nstc\nnot r0", 0xFF00, FLAG_N),
        ("mov r0, 1\nneg r0", 0xFFFF, FLAG_C | FLAG_N),
        ("mov r0, 0\nneg r0", 0, FLAG_Z),
        ("mov r0, 0x8000\nneg r0", 0x8000, FLAG_C | FLAG_N | FLAG_V),
        ("mov r0, 0x7FFF\nstc\ninc r0", 0x8000, FLAG_C | FLAG_N | FLAG_V),
        ("mov r0, 0xFFFF\ninc r0", 0, FLAG_Z),
        ("mov r0, 0x8000\ndec r0", 0x7FFF, FLAG_V),
        ("mov r0, 1\nstc\ndec r0", 0, FLAG_C | FLAG_Z),
        ("mov r0, 0x8001\nshl r0, 1", 0x0002, FLAG_C),
        ("mov r0, 0x0003\nshr r0, 1", 0x0001, FLAG_C),
        ("mov r0, 0x8000\nsar r0, 15", 0xFFFF, FLAG_N),
        ("mov r0, 0x4000\nsar r0, 2", 0x1000, 0),
        ("mov r0, 0x8001\nrol r0, 4", 0x0018, 0),
        ("mov r0, 0x0001\nror r0, 1", 0x8000, FLAG_C | FLAG_N),
        ("mov r0, 0x1234\nstc\nshl r0, 0", 0x1234, FLAG_C),
        ("mov r0, 0x1234\nmov r1, 0x14\nshl r0, r1", 0x2340, FLAG_C),
    ],
)
def test_arithmetic_logic_and_flags(source, result, flags):
    cpu = cpu_after(source)
    assert cpu.reg[0] == result
    assert cpu.flags & ~FLAG_I == flags


@pytest.mark.parametrize(
    ("source", "flags"),
    [
        ("mov r0, 5\ncmp r0, 5", FLAG_Z),
        ("mov r0, 5\ncmp r0, 6", FLAG_C | FLAG_N),
        ("mov r0, -1\ncmp r0, 1", FLAG_N),
        ("mov r0, 0x8000\ncmp r0, 1", FLAG_V),
        ("mov r0, 0x00F0\nstc\ntest r0, 0x0F00", FLAG_Z),
        ("mov r0, 0x8000\ntest r0, r0", FLAG_N),
    ],
)
def test_compare_and_test_leave_operands_alone(source, flags):
    cpu = cpu_after(source)
    assert cpu.flags & ~FLAG_I == flags
    assert cpu.reg[0] == int(source.split(",")[1].split("\n")[0], 0) & 0xFFFF


def test_mov_lea_push_and_pop_do_not_touch_flags():
    assert flags_of("stc\nmov r0, 0\nlea r1, [r0 + 1]\npush r0\npop r1") == FLAG_C


def _flag_value(code: int) -> int:
    c, z, n, v = (bool(code & bit) for bit in (FLAG_C, FLAG_Z, FLAG_N, FLAG_V))
    return (c, z, n, v)


EXPECTED_CONDITION = {
    "mp": lambda c, z, n, v: True,
    "eq": lambda c, z, n, v: z,
    "ne": lambda c, z, n, v: not z,
    "lo": lambda c, z, n, v: c,
    "hs": lambda c, z, n, v: not c,
    "mi": lambda c, z, n, v: n,
    "pl": lambda c, z, n, v: not n,
    "vs": lambda c, z, n, v: v,
    "vc": lambda c, z, n, v: not v,
    "hi": lambda c, z, n, v: not c and not z,
    "ls": lambda c, z, n, v: c or z,
    "ge": lambda c, z, n, v: n == v,
    "lt": lambda c, z, n, v: n != v,
    "gt": lambda c, z, n, v: not z and n == v,
    "le": lambda c, z, n, v: z or n != v,
}


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_condition_against_every_flag_combination(condition):
    for flags in range(16):
        cpu = cpu_after(
            f"""
            push {flags}
            popf
            mov r1, 0
            j{condition} taken
            halt
            taken:
            mov r1, 1
            """
        )
        assert bool(cpu.reg[1]) == EXPECTED_CONDITION[condition](*_flag_value(flags)), flags


@pytest.mark.parametrize(
    ("alias", "condition"),
    [("jz", "jeq"), ("jnz", "jne"), ("jc", "jlo"), ("jb", "jlo"), ("jnc", "jhs"), ("ja", "jhi")],
)
def test_condition_aliases_encode_identically(alias, condition):
    assert assemble(f"{alias} 0x200").segments == assemble(f"{condition} 0x200").segments


def test_jump_through_register_and_call_variants():
    cpu = cpu_after(
        """
            mov r1, second
            jmp r1
            halt
        second:
            mov r2, table
            call r2
            call [pointer]
            call [r2 + 4]
            call table
            jmp done
        table:
            inc r0
            ret
            .dw table
        pointer: .dw table
        done:
        """
    )
    assert cpu.reg[0] == 4
    assert cpu.sp == STACK_TOP


def test_push_every_source_and_pop_into_sp():
    cpu = cpu_after(
        """
        mov r1, 0x1111
        push r1
        push 0x2222
        push [value]
        push byte [value]
        mov r2, value
        push [r2]
        pop r3
        pop r4
        pop r5
        pop r0
        pop r1
        mov sp, 0x5000
        push 0x6000
        pop sp
        jmp end
        value: .dw 0x3344
        end:
        """
    )
    assert cpu.reg[3] == 0x3344
    assert cpu.reg[4] == 0x0044
    assert cpu.reg[5] == 0x3344
    assert cpu.reg[0] == 0x2222
    assert cpu.reg[1] == 0x1111
    assert cpu.sp == 0x6000


def test_pushf_popf_round_trip_and_mask():
    cpu = cpu_after("stc\nsti\npushf\nclc\ncli\npopf\npush 0xFFFF\npopf\npushf\npop r0")
    assert cpu.reg[0] == 0x020F


def test_flag_instructions():
    assert flags_of("stc") == FLAG_C
    assert flags_of("stc\nclc") == 0
    assert flags_of("cmc") == FLAG_C
    assert flags_of("stc\ncmc") == 0
    assert cpu_after("sti").flags & FLAG_I
    assert not cpu_after("sti\ncli").flags & FLAG_I


def test_nop_advances_pc_only():
    cpu = cpu_after("nop\nnop")
    assert cpu.pc == 0x106
    assert cpu.reg == [0] * 7 + [STACK_TOP]


def test_software_interrupt_handler_and_return():
    cpu = cpu_after(
        """
            .org 17 * 2
            .dw handler
            .org 0x100
            .entry start
        start:
            stc
            int 17
            jmp end
        handler:
            mov r0, 0x77
            pushf
            pop r1
            clc
            iret
        end:
        """
    )
    assert cpu.reg[0] == 0x77
    assert cpu.reg[1] & FLAG_I == 0
    assert cpu.flags & FLAG_C


def test_brk_traps_to_vector_three():
    cpu = cpu_after(
        """
            .org VEC_BREAK * 2
            .dw handler
            .org 0x100
            .entry start
        start:
            brk
            mov r1, 2
            jmp end
        handler:
            mov r0, [sp]
            iret
        end:
        """
    )
    assert cpu.reg[0] == 0x102
    assert cpu.reg[1] == 2


def test_divide_fault_handler_can_skip_the_instruction():
    cpu = cpu_after(
        """
            .org VEC_DIVIDE * 2
            .dw on_divide
            .org 0x100
            .entry start
        start:
            mov r0, 9
            div r0, 0
            mov r1, 1
            jmp end
        on_divide:
            mov r2, [sp]
            add r2, 4
            mov [sp], r2
            mov r3, 0xDEAD
            iret
        end:
        """
    )
    assert cpu.reg[3] == 0xDEAD
    assert cpu.reg[1] == 1
    assert cpu.reg[0] == 9


def test_bus_fault_on_unmapped_io_write():
    machine = execute("mov r0, 1\nmov [0xFFF0], r0")
    assert machine.cpu.fault == "unhandled bus fault at 0104"


def test_illegal_instruction_in_data():
    machine = execute("jmp data\ndata: .dw 0xFC00")
    assert machine.cpu.fault == "unhandled illegal instruction at 0104"


def test_in_and_out_through_ports():
    machine = execute(
        """
        mov r0, 'A'
        out SERIAL_DATA, r0
        mov r1, SERIAL_DATA
        mov r0, 'B'
        out r1, r0
        in r2, SERIAL_STATUS
        in r3, DISPLAY_COLS
        """
    )
    assert machine.serial.text == "AB"
    assert machine.cpu.reg[2] == 2
    assert machine.cpu.reg[3] == 80


def test_memory_mapped_display_and_keyboard():
    machine = Machine(seed=3)
    machine.load(
        assemble(
            """
            .include "lib/hw.inc"
            start:
                in r0, KBD_STATUS
                test r0, KBD_READY
                jz start
                in r0, KBD_DATA
                mov byte [TEXT_BASE + 81], r0
                mov byte [ATTR_BASE + 81], 0x4E
                halt
            """
        )
    )
    machine.run(5_000)
    assert not machine.cpu.halted
    machine.keyboard.type("Z")
    machine.run(5_000)
    assert machine.cpu.halted
    assert machine.display.text(1)[1] == "Z"
    assert machine.display.attrs(1)[1] == 0x4E


def test_wait_sleeps_until_the_timer_fires():
    machine = execute(
        """
            .org VEC_TIMER * 2
            .dw tick
            .org 0x100
            .entry start
        start:
            mov r0, 50
            out TIMER_RELOAD_L, r0
            mov r0, TIMER_ENABLE | TIMER_IRQ
            out TIMER_CTRL, r0
            sti
            wait
            jmp end
        tick:
            mov r5, 1
            iret
        end:
        """
    )
    assert machine.cpu.halted
    assert machine.cpu.reg[5] == 1
    assert machine.timer.status == 1


def test_masked_irq_stays_pending():
    machine = execute(
        """
            .org VEC_TIMER * 2
            .dw tick
            .org 0x100
            .entry start
        start:
            mov r0, 0
            out PIC_MASK, r0
            mov r0, 10
            out TIMER_RELOAD_L, r0
            mov r0, TIMER_ENABLE | TIMER_IRQ
            out TIMER_CTRL, r0
            sti
            mov r1, 20
        .spin:
            dec r1
            jnz .spin
            in r2, PIC_PENDING
            mov r0, IRQ_TIMER_BIT
            out PIC_ACK, r0
            in r3, PIC_PENDING
            jmp end
        tick:
            mov r5, 1
            iret
        end:
        """
    )
    assert machine.cpu.reg[5] == 0
    assert machine.cpu.reg[2] == 1
    assert machine.cpu.reg[3] == 0


def test_effective_addresses_wrap_at_16_bits():
    assert cpu_after("mov r1, 0xFFFF\nlea r0, [r1 + 3]").reg[0] == 2


def test_stack_growing_into_the_io_page_is_a_bus_fault():
    machine = execute("mov sp, 1\npush 0xABCD")
    assert machine.cpu.fault == "unhandled bus fault at 0104"
    assert machine.cpu.sp == 1

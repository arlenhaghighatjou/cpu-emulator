from cpuemulator.arch import FLAG_C, FLAG_I, FLAG_N, FLAG_V, FLAG_Z, IRQ_TIMER, STACK_TOP
from cpuemulator.bus import Bus
from cpuemulator.cpu import CPU
from cpuemulator.devices import InterruptController
from cpuemulator.instructions import BY_NAME, BYTE, CONDITIONS, Mode, encode


def op(name: str, mode: int = 0, rd: int = 0, rs: int = 0) -> int:
    return encode(BY_NAME[name].code, mode, rd, rs)


def boot(*words: int) -> CPU:
    bus = Bus()
    pic = InterruptController()
    bus.attach(pic)
    cpu = CPU(bus, pic)
    bus.load(0x100, b"".join(w.to_bytes(2, "little") for w in words))
    return cpu


def run(cpu: CPU, limit: int = 1000) -> CPU:
    while not cpu.halted and limit:
        cpu.step()
        limit -= 1
    return cpu


def jump(condition: str, target: int) -> tuple[int, int]:
    return op("j", CONDITIONS.index(condition)), target


def test_reset_state():
    cpu = boot()
    assert cpu.pc == 0x100
    assert cpu.sp == STACK_TOP
    assert cpu.flags == 0
    assert cpu.reg[:7] == [0] * 7


def test_mov_immediate_then_add_register():
    cpu = run(
        boot(op("mov", Mode.IMM, 0), 40, op("mov", Mode.IMM, 1), 2, op("add", 0, 0, 1), op("halt"))
    )
    assert cpu.reg[0] == 42
    assert cpu.instructions == 4


def test_add_overflow_sets_carry_and_zero():
    cpu = run(boot(op("mov", Mode.IMM, 0), 0xFFFF, op("add", Mode.IMM, 0), 1, op("halt")))
    assert cpu.reg[0] == 0
    assert cpu.flags == FLAG_C | FLAG_Z


def test_sub_borrow_and_signed_overflow():
    cpu = run(boot(op("mov", Mode.IMM, 0), 0x8000, op("sub", Mode.IMM, 0), 1, op("halt")))
    assert cpu.reg[0] == 0x7FFF
    assert cpu.flags == FLAG_V
    cpu = run(boot(op("mov", Mode.IMM, 0), 1, op("sub", Mode.IMM, 0), 2, op("halt")))
    assert cpu.reg[0] == 0xFFFF
    assert cpu.flags == FLAG_C | FLAG_N


def test_conditional_jump_uses_signed_compare():
    cpu = run(
        boot(
            op("mov", Mode.IMM, 0),
            0xFFFE,
            op("cmp", Mode.IMM, 0),
            3,
            *jump("lt", 0x10E),
            op("halt"),
            op("mov", Mode.IMM, 1),
            7,
            op("halt"),
        )
    )
    assert cpu.reg[1] == 7


def test_byte_store_and_indexed_load():
    cpu = run(
        boot(
            op("mov", Mode.IMM, 1),
            0x2000,
            op("storei", Mode.IDX | BYTE, 1),
            3,
            0x1AB,
            op("mov", Mode.IDX | BYTE, 0, 1),
            3,
            op("halt"),
        )
    )
    assert cpu.bus.ram[0x2003] == 0xAB
    assert cpu.bus.ram[0x2004] == 0
    assert cpu.reg[0] == 0xAB


def test_call_and_ret_use_the_stack():
    cpu = run(
        boot(op("call", Mode.IMM), 0x108, op("halt"), 0, op("mov", Mode.IMM, 2), 9, op("ret"))
    )
    assert cpu.reg[2] == 9
    assert cpu.pc == 0x106
    assert cpu.sp == STACK_TOP
    assert cpu.bus.read16(STACK_TOP - 2) == 0x104


def test_push_pop_order():
    cpu = run(
        boot(
            op("push", Mode.IMM),
            1,
            op("push", Mode.IMM),
            2,
            op("pop", 0, 0),
            op("pop", 0, 1),
            op("halt"),
        )
    )
    assert cpu.reg[0] == 2
    assert cpu.reg[1] == 1


def test_unhandled_divide_stops_with_fault():
    cpu = run(boot(op("mov", Mode.IMM, 0), 5, op("div", Mode.IMM, 0), 0, op("halt")))
    assert cpu.halted
    assert cpu.fault == "unhandled divide by zero at 0104"


def test_divide_fault_pushes_faulting_pc():
    cpu = boot(op("div", Mode.IMM, 0), 0, op("halt"))
    cpu.bus.write16(0x0000, 0x0300)
    cpu.bus.write16(0x0300, op("halt"))
    run(cpu)
    assert cpu.pc == 0x0302
    assert cpu.bus.read16(cpu.sp) == 0x100
    assert cpu.interrupts == 1


def test_illegal_instruction_fault():
    cpu = run(boot(0xFFFF))
    assert cpu.fault == "unhandled illegal instruction at 0100"


def test_unmapped_port_is_a_bus_fault():
    cpu = run(boot(op("in", Mode.IMM, 0), 0x99, op("halt")))
    assert cpu.fault == "unhandled bus fault at 0100"


def test_stack_in_io_page_double_faults():
    cpu = boot(op("mov", Mode.IMM, 7), 0xFF02, op("div", Mode.IMM, 0), 0)
    cpu.bus.write16(0x0000, 0x0300)
    run(cpu)
    assert cpu.fault.startswith("double fault")


def test_irq_waits_for_interrupt_enable():
    cpu = boot(op("wait"), op("halt"))
    cpu.bus.write16(0x0008, 0x0300)
    cpu.bus.load(
        0x0300,
        op("mov", Mode.IMM, 3).to_bytes(2, "little")
        + (5).to_bytes(2, "little")
        + op("iret").to_bytes(2, "little"),
    )
    cpu.step()
    cpu.pic.raise_irq(IRQ_TIMER)
    cpu.step()
    assert cpu.waiting
    cpu.flags |= FLAG_I
    run(cpu)
    assert cpu.reg[3] == 5
    assert cpu.flags & FLAG_I
    assert cpu.pic.pending == 0


def test_software_interrupt_and_iret_restore_flags():
    cpu = boot(op("stc"), op("int", 0, 1, 0), op("halt"))
    cpu.bus.write16(0x0010, 0x0300)
    cpu.bus.load(0x0300, op("clc").to_bytes(2, "little") + op("iret").to_bytes(2, "little"))
    run(cpu)
    assert cpu.flags == FLAG_C
    assert cpu.pc == 0x106


def test_idiv_overflow_sets_v():
    cpu = run(boot(op("mov", Mode.IMM, 0), 0x8000, op("idiv", Mode.IMM, 0), 0xFFFF, op("halt")))
    assert cpu.reg[0] == 0x8000
    assert cpu.flags & FLAG_V


def test_idiv_truncates_toward_zero():
    cpu = run(boot(op("mov", Mode.IMM, 0), (-7) & 0xFFFF, op("idiv", Mode.IMM, 0), 2, op("halt")))
    assert cpu.reg[0] == (-3) & 0xFFFF


def test_shl_carries_last_bit_out():
    cpu = run(boot(op("mov", Mode.IMM, 0), 0x4001, op("shl", Mode.IMM, 0), 2, op("halt")))
    assert cpu.reg[0] == 0x0004
    assert cpu.flags == FLAG_C


def test_op_counts_and_cycles():
    cpu = run(boot(op("mov", Mode.IMM, 0), 1, op("mov", Mode.ABS, 1), 0x2000, op("halt")))
    assert cpu.op_counts[BY_NAME["mov"].code] == 2
    assert cpu.cycles == 2 + 3 + 1

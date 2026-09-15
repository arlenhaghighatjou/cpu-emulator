from cpuemulator.arch import (
    FLAG_C,
    FLAG_I,
    FLAG_N,
    FLAG_V,
    FLAG_Z,
    FLAGS_MASK,
    IO_BASE,
    PROGRAM_BASE,
    SP,
    STACK_TOP,
    VEC_BREAK,
    VEC_BUS,
    VEC_DIVIDE,
    VEC_ILLEGAL,
    VEC_IRQ_BASE,
)
from cpuemulator.bus import Bus, BusFault
from cpuemulator.decoder import Decoded, decode_word
from cpuemulator.devices import InterruptController
from cpuemulator.instructions import BYTE, CONDITIONS, JUMP_IMM, OPS, Mode

INTERRUPT_CYCLES = 4
VECTOR_NAMES = ("divide by zero", "illegal instruction", "bus fault", "breakpoint")


def _condition_table() -> list[list[bool]]:
    rules = (
        lambda c, z, n, v: True,
        lambda c, z, n, v: z,
        lambda c, z, n, v: not z,
        lambda c, z, n, v: c,
        lambda c, z, n, v: not c,
        lambda c, z, n, v: n,
        lambda c, z, n, v: not n,
        lambda c, z, n, v: v,
        lambda c, z, n, v: not v,
        lambda c, z, n, v: not c and not z,
        lambda c, z, n, v: c or z,
        lambda c, z, n, v: n == v,
        lambda c, z, n, v: n != v,
        lambda c, z, n, v: not z and n == v,
        lambda c, z, n, v: z or n != v,
    )
    assert len(rules) == len(CONDITIONS)
    return [
        [bool(rule(f & FLAG_C, f & FLAG_Z, bool(f & FLAG_N), bool(f & FLAG_V))) for f in range(16)]
        for rule in rules
    ]


CONDITION_TABLE = _condition_table()


class Trap(Exception):
    def __init__(self, vector: int) -> None:
        super().__init__(vector)
        self.vector = vector


def _zn(value: int) -> int:
    return (FLAG_Z if value == 0 else 0) | (FLAG_N if value & 0x8000 else 0)


def _signed(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class CPU:
    def __init__(self, bus: Bus, pic: InterruptController | None = None) -> None:
        self.bus = bus
        self.pic = pic
        self.reg = [0] * 8
        self._handlers = [None] * 64
        for op in OPS:
            self._handlers[op.code] = getattr(self, f"_op_{op.name}")
        self.reset()

    def reset(self, entry: int = PROGRAM_BASE) -> None:
        self.reg = [0] * 8
        self.reg[SP] = STACK_TOP
        self.pc = entry
        self.flags = 0
        self.halted = False
        self.waiting = False
        self.fault: str | None = None
        self.cycles = 0
        self.instructions = 0
        self.interrupts = 0
        self.op_counts = [0] * 64

    @property
    def sp(self) -> int:
        return self.reg[SP]

    def step(self) -> int:
        if self.halted:
            return 0
        pic = self.pic
        if pic is not None and self.flags & FLAG_I and pic.pending & pic.mask:
            irq = pic.take()
            self.waiting = False
            self._enter(VEC_IRQ_BASE + irq, self.pc)
            self.cycles += INTERRUPT_CYCLES
            return INTERRUPT_CYCLES
        if self.waiting:
            self.cycles += 1
            return 1
        pc = self.pc
        bus = self.bus
        try:
            decoded = decode_word(bus.read16(pc))
            if decoded is None:
                raise Trap(VEC_ILLEGAL)
            ext = decoded.ext
            a = bus.read16((pc + 2) & 0xFFFF) if ext else 0
            b = bus.read16((pc + 4) & 0xFFFF) if ext == 2 else 0
            self.pc = (pc + 2 + 2 * ext) & 0xFFFF
            self._handlers[decoded.op.code](decoded, a, b)
        except Trap as trap:
            self.pc = pc
            self._enter(trap.vector, pc)
            self.cycles += INTERRUPT_CYCLES
            return INTERRUPT_CYCLES
        except BusFault:
            self.pc = pc
            self._enter(VEC_BUS, pc)
            self.cycles += INTERRUPT_CYCLES
            return INTERRUPT_CYCLES
        self.instructions += 1
        self.op_counts[decoded.op.code] += 1
        self.cycles += decoded.cycles
        return decoded.cycles

    def _enter(self, vector: int, return_pc: int) -> None:
        handler = self.bus.peek16(vector * 2)
        if handler == 0:
            name = VECTOR_NAMES[vector] if vector < len(VECTOR_NAMES) else f"vector {vector}"
            self._stop(f"unhandled {name} at {return_pc:04X}")
            return
        try:
            self._push(self.flags)
            self._push(return_pc)
        except BusFault:
            self._stop(f"double fault entering vector {vector} at {return_pc:04X}")
            return
        self.flags &= ~FLAG_I
        self.pc = handler
        self.interrupts += 1

    def _stop(self, reason: str) -> None:
        self.fault = reason
        self.halted = True

    def _push(self, value: int) -> None:
        sp = (self.reg[SP] - 2) & 0xFFFF
        self.bus.write16(sp, value)
        self.reg[SP] = sp

    def _pop(self) -> int:
        sp = self.reg[SP]
        value = self.bus.read16(sp)
        self.reg[SP] = (sp + 2) & 0xFFFF
        return value

    def _address(self, mode: int, base: int, a: int) -> int:
        kind = mode & 7
        if kind == Mode.IND:
            return self.reg[base]
        if kind == Mode.ABS:
            return a
        return (self.reg[base] + a) & 0xFFFF

    def _src(self, d: Decoded, a: int) -> int:
        kind = d.mode & 7
        if kind == Mode.REG:
            return self.reg[d.rs]
        if kind == Mode.IMM:
            return a
        address = self._address(d.mode, d.rs, a)
        if d.mode & BYTE:
            return self.bus.read8(address)
        return self.bus.read16(address)

    def _write(self, mode: int, address: int, value: int) -> None:
        if mode & BYTE:
            self.bus.write8(address, value)
        else:
            self.bus.write16(address, value)

    def _add(self, x: int, y: int, carry: int) -> int:
        total = x + y + carry
        result = total & 0xFFFF
        flags = (self.flags & FLAG_I) | _zn(result)
        if total > 0xFFFF:
            flags |= FLAG_C
        if (x ^ result) & (y ^ result) & 0x8000:
            flags |= FLAG_V
        self.flags = flags
        return result

    def _sub(self, x: int, y: int, borrow: int) -> int:
        total = x - y - borrow
        result = total & 0xFFFF
        flags = (self.flags & FLAG_I) | _zn(result)
        if total < 0:
            flags |= FLAG_C
        if (x ^ y) & (x ^ result) & 0x8000:
            flags |= FLAG_V
        self.flags = flags
        return result

    def _logic(self, result: int) -> int:
        self.flags = (self.flags & FLAG_I) | _zn(result)
        return result

    def _shift(self, result: int, carry: int | None) -> int:
        kept = self.flags & (FLAG_I | FLAG_C) if carry is None else self.flags & FLAG_I | carry
        self.flags = kept | _zn(result)
        return result

    def _op_nop(self, d: Decoded, a: int, b: int) -> None:
        pass

    def _op_halt(self, d: Decoded, a: int, b: int) -> None:
        self.halted = True

    def _op_wait(self, d: Decoded, a: int, b: int) -> None:
        self.waiting = True

    def _op_mov(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._src(d, a)

    def _op_store(self, d: Decoded, a: int, b: int) -> None:
        self._write(d.mode, self._address(d.mode, d.rd, a), self.reg[d.rs])

    def _op_storei(self, d: Decoded, a: int, b: int) -> None:
        value = b if d.ext == 2 else a
        self._write(d.mode, self._address(d.mode, d.rd, a), value)

    def _op_lea(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._address(d.mode, d.rs, a)

    def _op_xchg(self, d: Decoded, a: int, b: int) -> None:
        reg = self.reg
        reg[d.rd], reg[d.rs] = reg[d.rs], reg[d.rd]

    def _op_add(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._add(self.reg[d.rd], self._src(d, a), 0)

    def _op_adc(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._add(self.reg[d.rd], self._src(d, a), self.flags & FLAG_C)

    def _op_sub(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._sub(self.reg[d.rd], self._src(d, a), 0)

    def _op_sbc(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._sub(self.reg[d.rd], self._src(d, a), self.flags & FLAG_C)

    def _op_mul(self, d: Decoded, a: int, b: int) -> None:
        product = self.reg[d.rd] * self._src(d, a)
        result = product & 0xFFFF
        flags = (self.flags & FLAG_I) | _zn(result)
        if product >> 16:
            flags |= FLAG_C | FLAG_V
        self.flags = flags
        self.reg[d.rd] = result

    def _op_div(self, d: Decoded, a: int, b: int) -> None:
        divisor = self._src(d, a)
        if divisor == 0:
            raise Trap(VEC_DIVIDE)
        self.reg[d.rd] = self._logic(self.reg[d.rd] // divisor)

    def _op_idiv(self, d: Decoded, a: int, b: int) -> None:
        divisor = _signed(self._src(d, a))
        if divisor == 0:
            raise Trap(VEC_DIVIDE)
        dividend = _signed(self.reg[d.rd])
        if dividend == -0x8000 and divisor == -1:
            self.reg[d.rd] = self._logic(0x8000)
            self.flags |= FLAG_V
            return
        quotient = abs(dividend) // abs(divisor)
        if (dividend < 0) != (divisor < 0):
            quotient = -quotient
        self.reg[d.rd] = self._logic(quotient & 0xFFFF)

    def _op_mod(self, d: Decoded, a: int, b: int) -> None:
        divisor = self._src(d, a)
        if divisor == 0:
            raise Trap(VEC_DIVIDE)
        self.reg[d.rd] = self._logic(self.reg[d.rd] % divisor)

    def _op_and(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._logic(self.reg[d.rd] & self._src(d, a))

    def _op_or(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._logic(self.reg[d.rd] | self._src(d, a))

    def _op_xor(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._logic(self.reg[d.rd] ^ self._src(d, a))

    def _op_not(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._logic(~self.reg[d.rd] & 0xFFFF)

    def _op_neg(self, d: Decoded, a: int, b: int) -> None:
        value = self.reg[d.rd]
        result = -value & 0xFFFF
        flags = (self.flags & FLAG_I) | _zn(result)
        if value:
            flags |= FLAG_C
        if value == 0x8000:
            flags |= FLAG_V
        self.flags = flags
        self.reg[d.rd] = result

    def _op_inc(self, d: Decoded, a: int, b: int) -> None:
        result = (self.reg[d.rd] + 1) & 0xFFFF
        flags = (self.flags & (FLAG_I | FLAG_C)) | _zn(result)
        if result == 0x8000:
            flags |= FLAG_V
        self.flags = flags
        self.reg[d.rd] = result

    def _op_dec(self, d: Decoded, a: int, b: int) -> None:
        result = (self.reg[d.rd] - 1) & 0xFFFF
        flags = (self.flags & (FLAG_I | FLAG_C)) | _zn(result)
        if result == 0x7FFF:
            flags |= FLAG_V
        self.flags = flags
        self.reg[d.rd] = result

    def _op_shl(self, d: Decoded, a: int, b: int) -> None:
        value = self.reg[d.rd]
        count = self._src(d, a) & 15
        if not count:
            self.reg[d.rd] = self._shift(value, None)
            return
        carry = (value >> (16 - count)) & 1
        self.reg[d.rd] = self._shift((value << count) & 0xFFFF, carry)

    def _op_shr(self, d: Decoded, a: int, b: int) -> None:
        value = self.reg[d.rd]
        count = self._src(d, a) & 15
        if not count:
            self.reg[d.rd] = self._shift(value, None)
            return
        carry = (value >> (count - 1)) & 1
        self.reg[d.rd] = self._shift(value >> count, carry)

    def _op_sar(self, d: Decoded, a: int, b: int) -> None:
        value = self.reg[d.rd]
        count = self._src(d, a) & 15
        if not count:
            self.reg[d.rd] = self._shift(value, None)
            return
        carry = (value >> (count - 1)) & 1
        self.reg[d.rd] = self._shift((_signed(value) >> count) & 0xFFFF, carry)

    def _op_rol(self, d: Decoded, a: int, b: int) -> None:
        value = self.reg[d.rd]
        count = self._src(d, a) & 15
        if not count:
            self.reg[d.rd] = self._shift(value, None)
            return
        result = ((value << count) | (value >> (16 - count))) & 0xFFFF
        self.reg[d.rd] = self._shift(result, result & 1)

    def _op_ror(self, d: Decoded, a: int, b: int) -> None:
        value = self.reg[d.rd]
        count = self._src(d, a) & 15
        if not count:
            self.reg[d.rd] = self._shift(value, None)
            return
        result = ((value >> count) | (value << (16 - count))) & 0xFFFF
        self.reg[d.rd] = self._shift(result, result >> 15)

    def _op_cmp(self, d: Decoded, a: int, b: int) -> None:
        self._sub(self.reg[d.rd], self._src(d, a), 0)

    def _op_test(self, d: Decoded, a: int, b: int) -> None:
        self._logic(self.reg[d.rd] & self._src(d, a))

    def _op_push(self, d: Decoded, a: int, b: int) -> None:
        self._push(self._src(d, a))

    def _op_pop(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self._pop()

    def _op_pushf(self, d: Decoded, a: int, b: int) -> None:
        self._push(self.flags)

    def _op_popf(self, d: Decoded, a: int, b: int) -> None:
        self.flags = self._pop() & FLAGS_MASK

    def _op_j(self, d: Decoded, a: int, b: int) -> None:
        if CONDITION_TABLE[d.mode][self.flags & 0xF]:
            self.pc = a if d.rd == JUMP_IMM else self.reg[d.rs]

    def _op_call(self, d: Decoded, a: int, b: int) -> None:
        target = self._src(d, a)
        self._push(self.pc)
        self.pc = target

    def _op_ret(self, d: Decoded, a: int, b: int) -> None:
        self.pc = self._pop()

    def _op_int(self, d: Decoded, a: int, b: int) -> None:
        self._enter(d.rd << 3 | d.rs, self.pc)

    def _op_iret(self, d: Decoded, a: int, b: int) -> None:
        pc = self._pop()
        self.flags = self._pop() & FLAGS_MASK
        self.pc = pc

    def _op_brk(self, d: Decoded, a: int, b: int) -> None:
        self._enter(VEC_BREAK, self.pc)

    def _op_cli(self, d: Decoded, a: int, b: int) -> None:
        self.flags &= ~FLAG_I

    def _op_sti(self, d: Decoded, a: int, b: int) -> None:
        self.flags |= FLAG_I

    def _op_clc(self, d: Decoded, a: int, b: int) -> None:
        self.flags &= ~FLAG_C

    def _op_stc(self, d: Decoded, a: int, b: int) -> None:
        self.flags |= FLAG_C

    def _op_cmc(self, d: Decoded, a: int, b: int) -> None:
        self.flags ^= FLAG_C

    def _port(self, d: Decoded, a: int) -> int:
        port = a if d.mode == Mode.IMM else self.reg[d.rs]
        return IO_BASE + (port & 0xFF)

    def _op_in(self, d: Decoded, a: int, b: int) -> None:
        self.reg[d.rd] = self.bus.read8(self._port(d, a))

    def _op_out(self, d: Decoded, a: int, b: int) -> None:
        self.bus.write8(self._port(d, a), self.reg[d.rd])

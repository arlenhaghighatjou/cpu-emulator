# A7-16 architecture

A7-16 is a 16-bit little-endian CPU with eight registers, vectored interrupts and a
memory-mapped I/O page. This document is the reference the emulator, assembler and
disassembler are built against.

## Sizes

| Item          | Size                          |
| ------------- | ----------------------------- |
| Word          | 16 bits                       |
| Address space | 16 bits, 65536 bytes          |
| Byte order    | little-endian                 |
| Instruction   | 1 word + 0 to 2 extension words |

## Registers

| Name    | Index | Role                                             |
| ------- | ----- | ------------------------------------------------ |
| r0      | 0     | general, return value                            |
| r1-r3   | 1-3   | general, arguments                               |
| r4-r5   | 4-5   | general, callee saved                            |
| r6 / fp | 6     | general, frame pointer by convention             |
| r7 / sp | 7     | stack pointer, used implicitly by the stack ops  |
| pc      | -     | program counter                                  |
| flags   | -     | status register                                  |

### Flags

| Bit | Name | Meaning                          |
| --- | ---- | -------------------------------- |
| 0   | C    | carry out / borrow               |
| 1   | Z    | result is zero                   |
| 2   | N    | bit 15 of the result             |
| 3   | V    | signed overflow                  |
| 9   | I    | maskable interrupts enabled      |

All other bits read as zero. `popf` and `iret` mask the loaded value with `0x020F`.

## Memory map

| Range         | Use                                          |
| ------------- | -------------------------------------------- |
| `0000-003F`   | interrupt vector table, 32 little-endian words |
| `0040-00FF`   | system area                                  |
| `0100-DFFF`   | RAM, programs load at `0100` by default      |
| `E000-E7CF`   | character framebuffer, 80 x 25               |
| `E800-EFCF`   | attribute buffer, 80 x 25                    |
| `F000-FEFF`   | RAM                                          |
| `FF00-FFFF`   | I/O page                                     |

Everything below `FF00` is plain RAM, including the framebuffer. The display reads it
directly. Addresses wrap at 16 bits. Reading or writing an I/O address that no device
claims raises a bus fault.

## Reset state

| Item         | Value                          |
| ------------ | ------------------------------ |
| r0-r6        | 0                              |
| sp           | `E000`                         |
| flags        | 0, interrupts disabled         |
| pc           | image entry, `0100` if none    |
| RAM          | zero                           |
| devices      | reset to their power-on values |

## Instruction encoding

The first word of every instruction is split into four fields:

```
 15          10 9       6 5     3 2     0
+--------------+---------+-------+-------+
|    opcode    |  mode   |  rd   |  rs   |
+--------------+---------+-------+-------+
```

Extension words follow in this order: address or displacement, then immediate.

### Addressing modes

The low three bits of `mode` select how the operand is found. Bit 3 (`B`) selects byte
width for memory operands. Bytes are zero-extended on read and truncated on write.

| Value | Name | Syntax          | Operand                       | Ext words |
| ----- | ---- | --------------- | ----------------------------- | --------- |
| 0     | REG  | `r2`            | register `rs`                 | 0         |
| 1     | IMM  | `42`            | the extension word            | 1         |
| 2     | IND  | `[r2]`          | memory at `rs`                | 0         |
| 3     | ABS  | `[0x4000]`      | memory at the extension word  | 1         |
| 4     | IDX  | `[r2 + 8]`      | memory at `rs + disp`         | 1         |

Values 5-7 and `B` together with REG or IMM are illegal. For `store`, `storei` the
memory mode uses `rd` as its base register instead of `rs`.

Unused fields must be zero. Anything else is an illegal instruction.

### Opcodes

`src` is any addressing mode. `mem` is IND, ABS or IDX.

| Op   | Mnemonic | Form              | Effect                                   | Flags      |
| ---- | -------- | ----------------- | ---------------------------------------- | ---------- |
| 00   | nop      |                   |                                          | -          |
| 01   | halt     |                   | stop the machine                         | -          |
| 02   | wait     |                   | idle until an interrupt is taken         | -          |
| 03   | mov      | rd, src           | rd = src                                 | -          |
| 04   | store    | mem(rd), rs       | mem = rs                                 | -          |
| 05   | storei   | mem(rd), imm      | mem = imm                                | -          |
| 06   | lea      | rd, mem           | rd = effective address                   | -          |
| 07   | xchg     | rd, rs            | swap                                     | -          |
| 08   | add      | rd, src           | rd = rd + src                            | CZNV       |
| 09   | adc      | rd, src           | rd = rd + src + C                        | CZNV       |
| 0A   | sub      | rd, src           | rd = rd - src                            | CZNV       |
| 0B   | sbc      | rd, src           | rd = rd - src - C                        | CZNV       |
| 0C   | mul      | rd, src           | rd = low word of rd * src                | CZNV       |
| 0D   | div      | rd, src           | rd = rd / src unsigned                   | CZNV       |
| 0E   | idiv     | rd, src           | rd = rd / src signed, toward zero        | CZNV       |
| 0F   | mod      | rd, src           | rd = rd % src unsigned                   | CZNV       |
| 10   | and      | rd, src           | rd = rd & src                            | CZNV       |
| 11   | or       | rd, src           | rd = rd \| src                           | CZNV       |
| 12   | xor      | rd, src           | rd = rd ^ src                            | CZNV       |
| 13   | not      | rd                | rd = ~rd                                 | CZNV       |
| 14   | neg      | rd                | rd = -rd                                 | CZNV       |
| 15   | inc      | rd                | rd = rd + 1                              | ZNV        |
| 16   | dec      | rd                | rd = rd - 1                              | ZNV        |
| 17   | shl      | rd, src           | shift left                               | CZNV       |
| 18   | shr      | rd, src           | logical shift right                      | CZNV       |
| 19   | sar      | rd, src           | arithmetic shift right                   | CZNV       |
| 1A   | rol      | rd, src           | rotate left                              | CZNV       |
| 1B   | ror      | rd, src           | rotate right                             | CZNV       |
| 1C   | cmp      | rd, src           | flags of rd - src                        | CZNV       |
| 1D   | test     | rd, src           | flags of rd & src                        | CZNV       |
| 1E   | push     | src               | sp -= 2, [sp] = src                      | -          |
| 1F   | pop      | rd                | rd = [sp], sp += 2                       | -          |
| 20   | pushf    |                   | push flags                               | -          |
| 21   | popf     |                   | pop flags                                | all        |
| 22   | j*cc*    | target            | jump if condition `mode` holds           | -          |
| 23   | call     | src               | push return address, pc = src            | -          |
| 24   | ret      |                   | pop pc                                   | -          |
| 25   | int      | vector            | software interrupt, vector = rd:rs       | I cleared  |
| 26   | iret     |                   | pop pc, pop flags                        | all        |
| 27   | brk      |                   | breakpoint trap, vector 3                | I cleared  |
| 28   | cli      |                   | I = 0                                    | I          |
| 29   | sti      |                   | I = 1                                    | I          |
| 2A   | clc      |                   | C = 0                                    | C          |
| 2B   | stc      |                   | C = 1                                    | C          |
| 2C   | cmc      |                   | C = !C                                   | C          |
| 2D   | in       | rd, port          | rd = byte at `FF00 + port`               | -          |
| 2E   | out      | port, rd          | byte at `FF00 + port` = low byte of rd   | -          |

`call` with IMM jumps to the immediate; with REG to the register; with a memory mode it
loads the target word from memory. `in` and `out` take the port as IMM or REG (`rs`).

The jump target is selected by `rd`: 0 means an absolute IMM extension word, 1 means
register `rs`.

`int` accepts vectors 8-31. `mode` must be zero.

### Flag rules

- `add`, `adc`: C is the carry out of bit 15. V is set when both operands share a sign
  that the result does not.
- `sub`, `sbc`, `cmp`: C is the borrow, set when the unsigned subtrahend (plus carry)
  exceeds the minuend. V is set on signed overflow.
- `mul`: C and V are set when the high word of the 32-bit product is non-zero.
- `div`, `mod`: unsigned. A zero divisor raises the divide fault. C and V are cleared.
- `idiv`: signed, truncates toward zero. `8000 / FFFF` yields `8000` with V set.
- `and`, `or`, `xor`, `test`, `not`: C and V are cleared.
- `neg`: C is set unless the operand was zero. V is set when the operand was `8000`.
- `inc`, `dec`: C is preserved.
- Shifts and rotates: the count is `src & 15`. C is the last bit moved out, or
  unchanged when the count is zero. V is cleared.
- Z and N always reflect the stored (or compared) result for flag-setting ops.

### Conditions

| Code | Name | Aliases   | Holds when          |
| ---- | ---- | --------- | ------------------- |
| 0    | mp   |           | always              |
| 1    | eq   | z         | Z                   |
| 2    | ne   | nz        | !Z                  |
| 3    | lo   | c, b      | C                   |
| 4    | hs   | nc, ae    | !C                  |
| 5    | mi   |           | N                   |
| 6    | pl   |           | !N                  |
| 7    | vs   |           | V                   |
| 8    | vc   |           | !V                  |
| 9    | hi   | a         | !C and !Z           |
| 10   | ls   | be        | C or Z              |
| 11   | ge   |           | N == V              |
| 12   | lt   |           | N != V              |
| 13   | gt   |           | !Z and N == V       |
| 14   | le   |           | Z or N != V         |
| 15   |      |           | illegal             |

The mnemonic is `j` followed by the name, so condition 0 is `jmp`.

## Stack

The stack is full-descending through `sp`. A push decrements `sp` by two and then writes
a word. A pop reads a word and then increments `sp` by two. `call` pushes the address of
the next instruction.

## Interrupts

| Vector | Source                    | Kind      | Pushed pc              |
| ------ | ------------------------- | --------- | ---------------------- |
| 0      | divide by zero            | fault     | faulting instruction   |
| 1      | illegal instruction       | fault     | faulting instruction   |
| 2      | bus fault                 | fault     | faulting instruction   |
| 3      | `brk`                     | trap      | next instruction       |
| 4      | IRQ 0, timer              | interrupt | next instruction       |
| 5      | IRQ 1, keyboard           | interrupt | next instruction       |
| 6      | IRQ 2, serial receive     | interrupt | next instruction       |
| 7      | IRQ 3, unassigned         | interrupt | next instruction       |
| 8-31   | `int n`                   | trap      | next instruction       |

Entering an interrupt pushes flags, then pc, clears I and loads pc from the vector
table. `iret` reverses this. Faults and traps ignore I.

Hardware IRQs are latched by the interrupt controller. Between instructions, if I is
set, the lowest pending unmasked IRQ is taken and its pending bit is cleared. `wait`
stops fetching until that happens.

A vector entry of zero is unhandled. The CPU then stops in the fault state and reports
the cause. A fault raised while entering another interrupt is a double fault and also
stops the CPU.

## Cycles

Every instruction costs one cycle, plus one per extension word, plus one per memory
operand access. `mul` adds 4, `div`, `idiv` and `mod` add 8. Taking an interrupt costs 4.
Devices advance by the cycles consumed.

## I/O page

Ports are offsets from `FF00`. Undocumented addresses bus fault. Read-only registers
ignore writes.

### Keyboard, `FF00`

| Port | Name   | Access | Meaning                                         |
| ---- | ------ | ------ | ----------------------------------------------- |
| 00   | STATUS | r      | bit 0 key available, bit 1 FIFO overflowed      |
| 01   | DATA   | r      | pops the oldest key, 0 when empty               |
| 02   | CTRL   | rw     | bit 0 raise IRQ 1 when a key arrives            |
| 03   | COUNT  | r      | keys waiting                                    |

The FIFO holds 16 keys. Keys are ASCII. Enter is `0D`, backspace `08`, escape `1B`.
Up, down, left, right are `80`, `81`, `82`, `83`. Reading STATUS clears the overflow bit.

### Timer, `FF10`

| Port | Name     | Access | Meaning                                       |
| ---- | -------- | ------ | --------------------------------------------- |
| 10   | CTRL     | rw     | bit 0 enable, bit 1 periodic, bit 2 IRQ enable |
| 11   | STATUS   | rw     | bit 0 expired, write 1 to clear               |
| 12   | RELOAD_L | rw     | reload value, cycles                          |
| 13   | RELOAD_H | rw     |                                               |
| 14   | COUNT_L  | r      | current count                                 |
| 15   | COUNT_H  | r      |                                               |

Writing CTRL with bit 0 set loads COUNT from RELOAD. COUNT decrements once per cycle. On
reaching zero STATUS bit 0 is set, IRQ 0 is raised if enabled, and COUNT reloads when
periodic or the timer disables itself otherwise. A reload of zero counts 65536.

### Display, `FF20`

| Port | Name     | Access | Meaning                      |
| ---- | -------- | ------ | ---------------------------- |
| 20   | CURSOR_X | rw     | cursor column                |
| 21   | CURSOR_Y | rw     | cursor row                   |
| 22   | CTRL     | rw     | bit 0 cursor visible         |
| 23   | COLS     | r      | 80                           |
| 24   | ROWS     | r      | 25                           |

The character at row `y`, column `x` lives at `E000 + y * 80 + x`, its attribute at
`E800 + y * 80 + x`. The attribute's low nibble is the foreground colour and high nibble
the background. An attribute of `00` is drawn as `07`. Palette:

| 0 black | 1 blue | 2 green | 3 cyan | 4 red | 5 magenta | 6 brown | 7 light grey |
| 8 dark grey | 9 light blue | A light green | B light cyan | C light red | D pink | E yellow | F white |

### Interrupt controller, `FF30`

| Port | Name    | Access | Meaning                              |
| ---- | ------- | ------ | ------------------------------------ |
| 30   | PENDING | r      | bit n set when IRQ n is latched      |
| 31   | MASK    | rw     | bit n set enables IRQ n, resets to FF |
| 32   | ACK     | w      | clears the written pending bits      |

### Random number generator, `FF40`

| Port | Name   | Access | Meaning                                        |
| ---- | ------ | ------ | ---------------------------------------------- |
| 40   | DATA_L | r      | steps the generator, returns the low byte      |
| 41   | DATA_H | r      | high byte of the value latched by DATA_L       |
| 42   | SEED_L | w      | seed low byte                                  |
| 43   | SEED_H | w      | seed high byte, applies the seed               |

The generator is a 16-bit Galois LFSR with taps `B400`. A zero seed is replaced by
`ACE1`.

### Serial, `FF50`

| Port | Name   | Access | Meaning                                   |
| ---- | ------ | ------ | ----------------------------------------- |
| 50   | DATA   | rw     | write transmits, read pops a received byte |
| 51   | STATUS | r      | bit 0 byte received, bit 1 ready to send   |
| 52   | CTRL   | rw     | bit 0 raise IRQ 2 on receive               |

## Executable format

`.a7x` files are little-endian.

```
header
  4   magic "A7X\0"
  2   version, 1
  2   entry address
  2   segment count
  2   symbol count
  2   source file count
  4   line entry count
segment
  2   load address
  2   length (0 means 65536)
  n   bytes
symbol
  2   value
  1   name length
  n   UTF-8 name
source file
  2   path length
  n   UTF-8 path
line entry
  2   address
  2   source file index
  4   line number
```

Symbols and line entries are optional debug information and never affect execution.

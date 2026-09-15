# cpuemulator

A 16-bit computer built from scratch: the A7-16 CPU, an emulator for it, an assembler,
a disassembler, a debugger, memory-mapped devices and a Tic-Tac-Toe game with a minimax
opponent written entirely in A7 assembly.

The Python side only emulates hardware. Everything the game does, from reading keys to
drawing the board to choosing the computer's move, is machine code running on the CPU.

The architecture is specified in [docs/architecture.md](docs/architecture.md).

## Running

```
pip install -e .[dev]
cpuemulator run src/cpuemulator/programs/tictactoe/main.asm
cpuemulator run src/cpuemulator/programs/tictactoe/main.asm --display gui
cpuemulator run src/cpuemulator/programs/samples/fib.asm --display none
cpuemulator debug src/cpuemulator/programs/tictactoe/main.asm -b negamax
cpuemulator asm src/cpuemulator/programs/samples/hello.asm -o hello.a7x -l hello.lst
cpuemulator dis hello.a7x
```

`python -m cpuemulator` works the same way without installing.

## Tic-Tac-Toe

| Key                 | Action                          |
| ------------------- | ------------------------------- |
| 1-9                 | play that square                |
| arrows, enter/space | move the cursor and play        |
| D                   | cycle easy, medium, hard        |
| R                   | restart the round               |
| Q                   | quit                            |

Easy plays random squares from the hardware RNG. Medium takes wins, blocks, then prefers
the centre and corners. Hard opens like medium and then runs a recursive negamax search
with alpha-beta pruning, reporting how many positions it looked at.

## Layout

```
src/cpuemulator/
  arch.py instructions.py decoder.py   architecture constants, opcode table, decoding
  bus.py cpu.py devices.py display.py  hardware
  machine.py image.py                  system wiring and the .a7x format
  asm/                                 lexer, parser, two-pass assembler
  disassembler.py debugger.py shell.py tooling
  terminal.py gui.py cli.py            frontends
  programs/lib/                        hw.inc, std.asm, keys.asm
  programs/samples/                    small ROMs exercising the CPU
  programs/tictactoe/                  the game
```

## Debugger

`step [n]`, `next`, `finish`, `continue [cycles]`, `break <addr|symbol>`, `delete`,
`watch <addr> [r|w|rw]`, `regs`, `flags`, `stack [n]`, `x <addr> [len]`,
`dis [addr] [n]`, `trace on [file]|off|show`, `stats`, `set <reg> <value>`,
`poke <addr> <bytes>`, `key "text" enter up ...`, `screen`, `serial`, `symbols`, `reset`.

## Tests

```
pytest
ruff check .
ruff format --check .
```

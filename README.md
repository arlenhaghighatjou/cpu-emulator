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
cpuemulator debug src/cpuemulator/programs/samples/fib.asm
cpuemulator asm src/cpuemulator/programs/samples/hello.asm -o hello.a7x --listing
cpuemulator dis hello.a7x
```

`python -m cpuemulator` works the same way without installing.

## Tests

```
pytest
ruff check .
ruff format --check .
```

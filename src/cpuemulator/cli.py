import argparse
import sys
from pathlib import Path

from cpuemulator.asm import AsmError, Assembler
from cpuemulator.debugger import Debugger
from cpuemulator.disassembler import disassemble, label_names
from cpuemulator.image import Image, ImageError
from cpuemulator.machine import Machine

HEADLESS_BATCH = 200_000


def load_program(path: Path) -> Image:
    if path.suffix.lower() == ".a7x":
        return Image.load(path)
    return Assembler().assemble_file(path)


def cmd_asm(args: argparse.Namespace) -> int:
    assembler = Assembler()
    image = assembler.assemble_file(args.file)
    output = args.output or args.file.with_suffix(".a7x")
    image.save(output)
    print(f"{output}: {image.size} bytes, entry {image.entry:04X}, {len(image.symbols)} labels")
    if args.listing:
        args.listing.write_text(assembler.listing_text() + "\n", encoding="utf-8")
    if args.symbols:
        for name, value in sorted(image.symbols.items(), key=lambda item: item[1]):
            print(f"{value:04X}  {name}")
    return 0


def cmd_dis(args: argparse.Namespace) -> int:
    image = load_program(args.file)
    machine = Machine(seed=1)
    machine.load(image)
    names = label_names(image.symbols)
    read = machine.bus.peek16
    for start, data in image.segments:
        address = start
        end = start + len(data)
        while address < end:
            if address in names:
                print(f"{names[address]}:")
            ((at, words, text),) = disassemble(read, address, 1, names)
            hexes = " ".join(f"{w:04X}" for w in words)
            print(f"  {at:04X}  {hexes:<14}  {text}")
            address = at + 2 * len(words)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    machine = Machine(seed=args.seed)
    machine.load(load_program(args.file))
    if args.display == "terminal":
        from cpuemulator.terminal import Terminal

        Terminal(machine, args.hz).run()
    elif args.display == "gui":
        from cpuemulator.gui import Window

        Window(machine, args.hz).run()
    else:
        return _headless(machine, args)
    return _report(machine)


def _headless(machine: Machine, args: argparse.Namespace) -> int:
    cpu = machine.cpu
    debugger = None
    if args.trace:
        debugger = Debugger(machine)
        debugger.start_trace(args.trace)
    printed = 0
    while not cpu.halted and cpu.cycles < args.max_cycles:
        if machine.idle and not machine.timer.ctrl & 1:
            break
        if debugger is not None:
            debugger.step(1000)
        else:
            machine.run(min(HEADLESS_BATCH, args.max_cycles - cpu.cycles))
        output = machine.serial.output
        if len(output) > printed:
            sys.stdout.write(output[printed:].decode("latin-1"))
            sys.stdout.flush()
            printed = len(output)
    if debugger is not None:
        debugger.stop_trace()
    if args.screen:
        print(machine.display.dump())
    return _report(machine)


def _report(machine: Machine) -> int:
    cpu = machine.cpu
    state = "halted" if cpu.halted else "waiting for input" if machine.idle else "stopped"
    print(
        f"{state} at {cpu.pc:04X} after {cpu.instructions} instructions, {cpu.cycles} cycles",
        file=sys.stderr,
    )
    if cpu.fault:
        print(f"fault: {cpu.fault}", file=sys.stderr)
        return 1
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    from cpuemulator.shell import Shell

    machine = Machine(seed=args.seed)
    machine.load(load_program(args.file))
    debugger = Debugger(machine)
    for target in args.breakpoint:
        debugger.breakpoints.add(debugger.resolve(target))
    shell = Shell(debugger)
    shell.intro = f"{Shell.intro}\n{debugger.current()}"
    shell.cmdloop()
    debugger.stop_trace()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpuemulator", description="A7-16 toolchain and emulator")
    commands = parser.add_subparsers(dest="command", required=True)

    asm = commands.add_parser("asm", help="assemble a source file into an A7X image")
    asm.add_argument("file", type=Path)
    asm.add_argument("-o", "--output", type=Path)
    asm.add_argument("-l", "--listing", type=Path, help="write a listing file")
    asm.add_argument("--symbols", action="store_true", help="print the symbol table")
    asm.set_defaults(handler=cmd_asm)

    run = commands.add_parser("run", help="run a source file or A7X image")
    run.add_argument("file", type=Path)
    run.add_argument("--display", choices=("terminal", "gui", "none"), default="terminal")
    run.add_argument("--hz", type=int, default=2_000_000, help="emulated clock rate in cycles/s")
    run.add_argument("--seed", type=int, help="seed for the random number generator")
    run.add_argument("--max-cycles", type=int, default=500_000_000, help="headless cycle limit")
    run.add_argument("--trace", type=Path, help="write an instruction trace (headless only)")
    run.add_argument("--screen", action="store_true", help="print the screen when headless")
    run.set_defaults(handler=cmd_run)

    debug = commands.add_parser("debug", help="open the interactive debugger")
    debug.add_argument("file", type=Path)
    debug.add_argument("-b", "--breakpoint", action="append", default=[])
    debug.add_argument("--seed", type=int)
    debug.set_defaults(handler=cmd_debug)

    dis = commands.add_parser("dis", help="disassemble a source file or A7X image")
    dis.add_argument("file", type=Path)
    dis.set_defaults(handler=cmd_dis)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (AsmError, ImageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
    except OSError as exc:
        print(f"error: {exc.filename}: {exc.strerror}", file=sys.stderr)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
    return 1

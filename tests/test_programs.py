from pathlib import Path

import pytest

from cpuemulator.asm import assemble_file
from cpuemulator.asm.assembler import LIBRARY
from cpuemulator.machine import Machine

SAMPLES = LIBRARY / "samples"


def boot(path: Path) -> Machine:
    machine = Machine(seed=7)
    machine.load(assemble_file(path))
    return machine


def settle(machine: Machine, budget: int = 20_000_000) -> Machine:
    cpu = machine.cpu
    while not cpu.halted and cpu.cycles < budget:
        machine.run(100_000)
        if machine.idle and not machine.timer.ctrl & 1:
            break
    return machine


def run_sample(name: str) -> Machine:
    machine = settle(boot(SAMPLES / f"{name}.asm"))
    assert machine.cpu.halted
    assert machine.cpu.fault is None
    return machine


@pytest.mark.parametrize("path", sorted(SAMPLES.glob("*.asm")), ids=lambda p: p.stem)
def test_every_sample_assembles(path):
    assert assemble_file(path).size > 0


def test_arith():
    assert run_sample("arith").serial.text == (
        "add 5555\n"
        "sub 999\n"
        "mul 3000\n"
        "div 7142 rem 6\n"
        "idiv -14\n"
        "carry yes\n"
        "overflow yes\n"
        "bits 255\n"
        "rotate 3\n"
        "neg -5\n"
    )


def test_loop():
    assert run_sample("loop").serial.text == "1 2 3 4 5 6 7 8 9 10 \nsum 55\n54321\n"


def test_fibonacci_until_16_bit_overflow():
    numbers = [0, 1]
    while numbers[-1] + numbers[-2] <= 0xFFFF:
        numbers.append(numbers[-1] + numbers[-2])
    expected = "".join(f"{n}\n" for n in numbers)
    assert run_sample("fib").serial.text == expected


def test_memcpy():
    machine = run_sample("memcpy")
    assert machine.serial.text == "memory copy works\nababcd\naabcdd\n*****\n17\n"
    assert bytes(machine.bus.ram[0x4000:0x4012]) == b"memory copy works\0"


def test_stack_recursion_and_frames():
    assert run_sample("stack").serial.text == (
        "fact 8 = 40320\nsum 100 = 5050\npop 321\nflags kept\nsp 57344\n"
    )


def test_hello_writes_the_framebuffer():
    machine = run_sample("hello")
    display = machine.display
    assert display.text(10)[33:46] == "Hello, world!"
    assert display.attrs(10)[33] == 0x1F
    assert display.text(12).strip() == "running on the A7-16 CPU"
    assert display.attrs(12)[28] == 0x1E
    assert [display.attrs(15)[24 + 2 * i] for i in range(16)] == [i << 4 for i in range(16)]
    assert display.cursor_visible


def test_timer_interrupts():
    machine = run_sample("timer")
    assert machine.serial.text == "".join(f"tick {n}\n" for n in (10, 20, 30, 40, 50))
    assert machine.cpu.interrupts >= 50


def test_keyecho_reads_the_keyboard_through_interrupts():
    machine = boot(SAMPLES / "keyecho.asm")
    settle(machine)
    assert machine.idle
    machine.keyboard.type("hi")
    machine.keyboard.press(0x0D)
    settle(machine)
    machine.keyboard.type("a7")
    machine.keyboard.press(0x1B)
    settle(machine)
    assert machine.cpu.halted
    assert machine.serial.text == "hi\na7"
    assert machine.display.text(0).startswith("type something, escape quits")
    assert machine.display.text(1).startswith("hi")
    assert machine.display.text(2).startswith("a7")

from cpuemulator.arch import IRQ_KEYBOARD, IRQ_SERIAL, IRQ_TIMER, KEY_UP, TEXT_BASE
from cpuemulator.devices import InterruptController, Keyboard, Rng, Serial, Timer
from cpuemulator.display import Display


def test_pic_takes_lowest_unmasked_irq_first():
    pic = InterruptController()
    pic.raise_irq(2)
    pic.raise_irq(1)
    pic.write(1, 0b100)
    assert pic.take() == 2
    assert pic.pending == 0b010


def test_pic_ack_clears_pending_bits():
    pic = InterruptController()
    pic.raise_irq(0)
    pic.raise_irq(3)
    pic.write(2, 0b1000)
    assert pic.read(0) == 1


def test_keyboard_fifo_order_and_status():
    keyboard = Keyboard(InterruptController())
    keyboard.type("ab")
    keyboard.press(KEY_UP)
    assert keyboard.read(3) == 3
    assert keyboard.read(0) == 1
    assert [keyboard.read(1) for _ in range(4)] == [ord("a"), ord("b"), KEY_UP, 0]
    assert keyboard.read(0) == 0


def test_keyboard_overflow_is_reported_once():
    keyboard = Keyboard(InterruptController())
    keyboard.type("x" * 17)
    assert keyboard.read(3) == 16
    assert keyboard.read(0) == 3
    assert keyboard.read(0) == 1


def test_keyboard_irq_only_when_enabled():
    pic = InterruptController()
    keyboard = Keyboard(pic)
    keyboard.press(1)
    assert pic.pending == 0
    keyboard.write(2, 1)
    keyboard.press(1)
    assert pic.pending == 1 << IRQ_KEYBOARD


def test_one_shot_timer_expires_and_stops():
    pic = InterruptController()
    timer = Timer(pic)
    timer.write(2, 10)
    timer.write(0, 0b101)
    timer.tick(9)
    assert timer.status == 0
    assert timer.read(4) == 1
    timer.tick(3)
    assert timer.status == 1
    assert pic.pending == 1 << IRQ_TIMER
    assert timer.ctrl & 1 == 0


def test_periodic_timer_reloads_with_overshoot():
    timer = Timer(InterruptController())
    timer.write(2, 10)
    timer.write(0, 0b011)
    timer.tick(13)
    assert timer.count == 7
    assert timer.ctrl & 1
    timer.write(1, 1)
    assert timer.status == 0


def test_timer_zero_reload_counts_full_range():
    timer = Timer(InterruptController())
    timer.write(0, 1)
    assert timer.count == 0x10000


def test_rng_is_deterministic_and_reseedable():
    rng = Rng()
    first = [rng.read(0) | rng.read(1) << 8 for _ in range(4)]
    rng.reset()
    assert [rng.read(0) | rng.read(1) << 8 for _ in range(4)] == first
    rng.write(2, 0x34)
    rng.write(3, 0x12)
    assert rng.state == 0x1234
    rng.write(2, 0)
    rng.write(3, 0)
    assert rng.state == 0xACE1


def test_rng_has_full_period():
    rng = Rng()
    start = rng.state
    steps = 1
    while rng.next() != start:
        steps += 1
    assert steps == 0xFFFF


def test_serial_transmit_and_receive():
    pic = InterruptController()
    serial = Serial(pic)
    serial.write(0, ord("h"))
    serial.write(0, ord("i"))
    assert serial.text == "hi"
    serial.write(2, 1)
    serial.receive(b"z")
    assert pic.pending == 1 << IRQ_SERIAL
    assert serial.read(1) == 3
    assert serial.read(0) == ord("z")
    assert serial.read(1) == 2


def test_display_reads_framebuffer_ram():
    ram = bytearray(0x10000)
    display = Display(ram)
    ram[TEXT_BASE + 81 : TEXT_BASE + 84] = b"A7!"
    assert display.text(1).startswith(" A7!")
    assert display.read(3) == 80
    assert display.read(4) == 25
    display.write(0, 5)
    assert display.cursor_x == 5

from cpuemulator.arch import KEY_BACKSPACE, KEY_ENTER, KEY_ESCAPE, KEY_UP
from cpuemulator.asm.assembler import LIBRARY
from cpuemulator.cli import main
from cpuemulator.terminal import render_row, translate

SAMPLES = LIBRARY / "samples"


def test_translate_escape_sequences_and_control_keys():
    keys = translate("a\x1b[A\r\x7f\x1b")
    assert keys == [ord("a"), KEY_UP, KEY_ENTER, KEY_BACKSPACE, KEY_ESCAPE]


def test_render_row_groups_runs_of_the_same_attribute():
    assert render_row(b"AB\x01", bytes([0x1F, 0x1F, 0x4E])) == "\x1b[97;44mAB\x1b[93;41m "


def test_render_row_draws_zero_attribute_as_light_grey():
    assert render_row(b"x", b"\x00") == "\x1b[37;40mx"


def test_asm_writes_image_listing_and_symbols(tmp_path, capsys):
    source = tmp_path / "prog.asm"
    source.write_text("start:\n    mov r0, 1\n    halt\n")
    image = tmp_path / "prog.a7x"
    listing = tmp_path / "prog.lst"
    assert main(["asm", str(source), "-o", str(image), "-l", str(listing), "--symbols"]) == 0
    out = capsys.readouterr().out
    assert "6 bytes, entry 0100, 1 labels" in out
    assert "0100  start" in out
    assert image.read_bytes().startswith(b"A7X\0")
    assert "mov r0, 1" in listing.read_text()


def test_dis_reads_images(tmp_path, capsys):
    source = tmp_path / "prog.asm"
    source.write_text("start:\n    mov r0, 1\n    jmp start\n")
    main(["asm", str(source), "-o", str(tmp_path / "prog.a7x")])
    capsys.readouterr()
    assert main(["dis", str(tmp_path / "prog.a7x")]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "start:"
    assert out[1].endswith("mov r0, 1")
    assert out[2].endswith("jmp start")


def test_headless_run_streams_serial_output(capsys):
    assert main(["run", str(SAMPLES / "fib.asm"), "--display", "none"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("0\n1\n1\n2\n3\n5\n")
    assert captured.err.startswith("halted at")


def test_headless_run_can_print_the_screen(capsys):
    assert main(["run", str(SAMPLES / "hello.asm"), "--display", "none", "--screen"]) == 0
    assert "Hello, world!" in capsys.readouterr().out


def test_headless_run_stops_when_waiting_for_input(capsys):
    assert main(["run", str(SAMPLES / "keyecho.asm"), "--display", "none"]) == 0
    assert capsys.readouterr().err.startswith("waiting for input")


def test_headless_trace_file(tmp_path, capsys):
    trace = tmp_path / "trace.log"
    assert main(["run", str(SAMPLES / "loop.asm"), "--display", "none", "--trace", str(trace)]) == 0
    lines = trace.read_text().splitlines()
    assert "mov r4, 1" in lines[0]
    assert any("call ser_putu" in line for line in lines)


def test_run_reports_faults_with_exit_code(tmp_path, capsys):
    source = tmp_path / "bad.asm"
    source.write_text("mov r0, 1\ndiv r0, 0\n")
    assert main(["run", str(source), "--display", "none"]) == 1
    assert "fault: unhandled divide by zero at 0104" in capsys.readouterr().err


def test_assembly_errors_are_reported_with_location(tmp_path, capsys):
    source = tmp_path / "bad.asm"
    source.write_text("nop\n  bogus r1\n")
    assert main(["asm", str(source)]) == 1
    assert capsys.readouterr().err == f"error: {source}:2:3: unknown instruction 'bogus'\n"


def test_missing_file_is_reported(tmp_path, capsys):
    assert main(["run", str(tmp_path / "missing.a7x"), "--display", "none"]) == 1
    assert "missing.a7x" in capsys.readouterr().err

import pytest

from cpuemulator.image import Image, ImageError


def sample() -> Image:
    return Image(
        entry=0x0120,
        segments=[(0x0000, b"\x20\x01"), (0x0100, bytes(range(40)))],
        symbols={"start": 0x0120, "main.loop": 0x0124},
        files=["main.asm", "lib/std.asm"],
        lines={0x0120: (0, 3), 0x0124: (1, 70000)},
    )


def test_round_trip_preserves_everything():
    image = sample()
    assert Image.from_bytes(image.to_bytes()) == image


def test_source_lookup():
    image = sample()
    assert image.source(0x0124) == ("lib/std.asm", 70000)
    assert image.source(0x0122) is None


def test_save_and_load(tmp_path):
    path = tmp_path / "game.a7x"
    sample().save(path)
    assert path.read_bytes().startswith(b"A7X\0")
    assert Image.load(path) == sample()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"A7X", "too short"),
        (b"ELF\0" + bytes(14), "not an A7X image"),
        (b"A7X\0\x02\x00" + bytes(12), "unsupported A7X version 2"),
    ],
)
def test_rejects_bad_headers(data, message):
    with pytest.raises(ImageError, match=message):
        Image.from_bytes(data)


def test_rejects_truncated_and_trailing_data():
    data = sample().to_bytes()
    with pytest.raises(ImageError):
        Image.from_bytes(data[:-3])
    with pytest.raises(ImageError, match="trailing"):
        Image.from_bytes(data + b"\0")

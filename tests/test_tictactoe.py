import random
from collections.abc import Callable
from functools import cache

import pytest

from cpuemulator.arch import KEY_ENTER, KEY_LEFT, KEY_UP
from cpuemulator.asm import assemble_file
from cpuemulator.asm.assembler import LIBRARY
from cpuemulator.debugger import Debugger
from cpuemulator.image import Image
from cpuemulator.machine import Machine

GAME = LIBRARY / "tictactoe" / "main.asm"
BOARD_X = 31
BOARD_Y = 5
STATUS_ROW = 18
SCORE_ROW = 20
LEVEL_ROW = 21
STATS_ROW = 22
RESULTS = ("You win!", "Computer wins!", "It's a draw")
LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))


@pytest.fixture(scope="module")
def image() -> Image:
    return assemble_file(GAME)


class Game:
    def __init__(self, image: Image, seed: int = 11) -> None:
        self.machine = Machine(seed=seed)
        self.machine.load(image)
        self.symbols = image.symbols
        self.settle()

    def ram(self, name: str, offset: int = 0) -> int:
        return self.machine.bus.ram[self.symbols[name] + offset]

    def settle(self, limit: int = 40_000_000) -> None:
        machine = self.machine
        start = machine.cpu.cycles
        while not machine.cpu.halted:
            machine.run(50_000)
            idle = machine.cpu.waiting and not machine.keyboard.keys
            if idle and self.ram("kb_head") == self.ram("kb_tail"):
                return
            assert machine.cpu.cycles - start < limit, "game did not settle"

    def press(self, *keys: str | int) -> None:
        for key in keys:
            codes = [ord(c) for c in key] if isinstance(key, str) else [key]
            for code in codes:
                self.machine.keyboard.press(code)
                self.settle()

    def board(self) -> list[int]:
        return [self.ram("board", i) for i in range(9)]

    def screen_cells(self) -> str:
        display = self.machine.display
        marks = {"\\": "X", "/": "O"}
        cells = []
        for cell in range(9):
            row, col = divmod(cell, 3)
            text = display.text(BOARD_Y + row * 4)
            cells.append(marks.get(text[BOARD_X + 1 + col * 6], "."))
        return "".join(cells)

    def cell_attr(self, cell: int) -> int:
        row, col = divmod(cell, 3)
        return self.machine.display.attrs(BOARD_Y + 1 + row * 4)[BOARD_X + col * 6]

    def row(self, y: int) -> str:
        return self.machine.display.text(y).strip()

    @property
    def status(self) -> str:
        return self.row(STATUS_ROW)


def winner(board: tuple[int, ...]) -> int:
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return 3 if all(board) else 0


@cache
def score(board: tuple[int, ...], side: int) -> int:
    result = winner(board)
    if result == 3:
        return 0
    if result:
        return 1 if result == side else -1
    best = -2
    for cell in range(9):
        if not board[cell]:
            child = (*board[:cell], side, *board[cell + 1 :])
            best = max(best, -score(child, 3 - side))
    return best


def perfect(board: list[int]) -> int:
    state = tuple(board)
    moves = [c for c in range(9) if not board[c]]
    return max(moves, key=lambda c: -score((*state[:c], 1, *state[c + 1 :]), 2))


def first_empty(board: list[int]) -> int:
    return board.index(0)


def last_empty(board: list[int]) -> int:
    return 8 - board[::-1].index(0)


def play_round(game: Game, choose: Callable[[list[int]], int]) -> str:
    while game.status not in RESULTS:
        assert game.status == "Your move, you are X"
        board = game.board()
        move = choose(board)
        game.press(str(move + 1))
        after = game.board()
        assert after[move] == 1
        assert game.screen_cells() == "".join(".XO"[v] for v in after)
    return game.status


def test_boot_draws_an_empty_board(image):
    game = Game(image)
    assert game.status == "Your move, you are X"
    assert game.board() == [0] * 9
    assert game.screen_cells() == "." * 9
    assert game.row(1) == "T I C - T A C - T O E"
    assert "hard" in game.row(LEVEL_ROW)
    top = game.machine.display.text(BOARD_Y)
    assert [top[BOARD_X + col * 6] for col in range(3)] == ["1", "2", "3"]
    assert not game.machine.cpu.halted


def test_number_key_places_x_and_computer_replies(image):
    game = Game(image)
    game.press("5")
    board = game.board()
    assert board[4] == 1
    assert board.count(2) == 1
    assert game.screen_cells() == "".join(".XO"[v] for v in board)
    assert game.status == "Your move, you are X"


def test_hard_mode_reports_its_search(image):
    game = Game(image)
    game.press("5")
    assert game.row(STATS_ROW) == ""
    game.press(str(game.board().index(0) + 1))
    assert game.row(STATS_ROW).startswith("last search: ")
    assert "positions, computer expects" in game.row(STATS_ROW)
    assert game.ram("ai_nodes") | game.ram("ai_nodes", 1) << 8 > 0


def test_occupied_square_is_rejected(image):
    game = Game(image)
    game.press("5")
    before = game.board()
    game.press("5")
    assert game.status == "That square is already taken"
    assert game.board() == before


def test_arrow_keys_move_the_cursor_and_enter_selects(image):
    game = Game(image)
    game.press(KEY_UP, KEY_LEFT)
    assert game.ram("cursor") == 0
    assert game.cell_attr(0) >> 4 in (0, 1)
    game.press(KEY_ENTER)
    assert game.board()[0] == 1


def test_difficulty_cycles_through_levels(image):
    game = Game(image)
    game.press("d")
    assert "easy" in game.row(LEVEL_ROW)
    game.press("D")
    assert "medium" in game.row(LEVEL_ROW)
    game.press("d")
    assert "hard" in game.row(LEVEL_ROW)


def test_medium_blocks_then_takes_the_win(image):
    game = Game(image)
    game.press("d", "d")
    game.press("1")
    assert game.board()[4] == 2
    game.press("2")
    assert game.board()[2] == 2
    game.press("9")
    assert game.board()[6] == 2
    assert game.status == "Computer wins!"
    assert "Computer  1" in game.row(SCORE_ROW)
    for cell in (2, 4, 6):
        assert game.cell_attr(cell) >> 4 == 2


def test_player_win_is_detected_by_the_program(image):
    game = Game(image)
    game.press("d", "d")
    game.press("1")
    game.press("9")
    game.press("7")
    assert game.board() == [1, 0, 2, 0, 2, 0, 1, 2, 1]
    game.press("4")
    assert game.status == "You win!"
    assert "You  1" in game.row(SCORE_ROW)
    for cell in (0, 3, 6):
        assert game.cell_attr(cell) >> 4 == 2


def test_win_detection_reads_the_board_from_emulated_ram(image):
    game = Game(image)
    bus = game.machine.bus
    bus.write8(image.symbols["board"], 1)
    bus.write8(image.symbols["board"] + 1, 1)
    game.press("3")
    assert game.status == "You win!"


def test_perfect_player_draws_hard_mode_and_round_restarts(image):
    game = Game(image)
    assert play_round(game, perfect) == "It's a draw"
    assert "Draws  1" in game.row(SCORE_ROW)
    game.press(KEY_ENTER)
    board = game.board()
    assert board.count(2) == 1
    assert board[4] == 2
    assert game.status == "Your move, you are X"
    assert play_round(game, perfect) == "It's a draw"


@pytest.mark.parametrize("strategy", [first_empty, last_empty], ids=lambda s: s.__name__)
def test_hard_mode_never_loses(image, strategy):
    game = Game(image)
    for _ in range(2):
        assert play_round(game, strategy) != "You win!"
        game.press("r")


def test_hard_mode_beats_random_players(image):
    rng = random.Random(1234)
    game = Game(image)
    results = []
    for _ in range(4):
        results.append(play_round(game, lambda b: rng.choice([c for c in range(9) if not b[c]])))
        game.press(KEY_ENTER)
    assert "You win!" not in results
    assert "Computer wins!" in results


def test_easy_mode_plays_legal_random_moves(image):
    game = Game(image, seed=99)
    game.press("d")
    assert play_round(game, first_empty) in RESULTS


def test_restart_clears_the_board(image):
    game = Game(image)
    game.press("5", "r")
    assert game.board() == [0] * 9
    assert game.status == "Your move, you are X"


def test_debugger_can_stop_inside_the_minimax_search(image):
    game = Game(image)
    game.press("5")
    debugger = Debugger(game.machine)
    debugger.breakpoints.add(image.symbols["negamax"])
    game.machine.keyboard.press(ord(str(game.board().index(0) + 1)))
    assert debugger.cont(limit=5_000_000).startswith("breakpoint at")
    assert "<negamax>" in debugger.current()
    assert debugger.cont(limit=5_000_000).startswith("breakpoint at")
    assert "call negamax" in debugger.disassembly(image.symbols["negamax"], 60)
    debugger.breakpoints.clear()
    while debugger.cont(limit=5_000_000) != "waiting for an interrupt":
        pass
    assert game.board().count(2) == 2
    assert debugger.cpu.op_counts[0x22] > 0


def test_quit_halts_the_cpu(image):
    game = Game(image)
    game.press("q")
    assert game.machine.cpu.halted
    assert game.machine.cpu.fault is None
    assert game.status == "Thanks for playing"

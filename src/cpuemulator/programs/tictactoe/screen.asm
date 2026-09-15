.include "lib/hw.inc"
.include "tictactoe/ai.asm"

BOARD_X = 31
BOARD_Y = 5
TITLE_ROW = 1
STATUS_ROW = 18
PROMPT_ROW = 19
SCORE_ROW = 20
LEVEL_ROW = 21
STATS_ROW = 22
HELP_ROW = 24

ATTR_X = LIGHT_CYAN
ATTR_O = LIGHT_RED
CURSOR_BG = BLUE << 4
WIN_BG = GREEN << 4

cursor: .db 4
show_cursor: .db 0
blink: .db 1
wins: .dw 0
losses: .dw 0
draws: .dw 0

glyph_x: .ascii "\\ / X / \\"
glyph_o: .ascii "/-\\| |\\-/"

clear_row:
    mul r0, SCREEN_COLS
    mov r1, SCREEN_COLS
.fill:
    mov byte [r0 + TEXT_BASE], ' '
    mov byte [r0 + ATTR_BASE], LIGHT_GREY
    inc r0
    dec r1
    jnz .fill
    ret

print_center:
    push r4
    push r5
    mov r4, r0
    mov r5, r1
    mov r0, r2
    call con_color
    mov r0, r5
    call clear_row
    mov r0, r4
    call str_len
    mov r1, SCREEN_COLS
    sub r1, r0
    shr r1, 1
    mov r0, r1
    mov r1, r5
    mov r2, r4
    call con_print_at
    pop r5
    pop r4
    ret

set_status:
    mov r2, r1
    mov r1, STATUS_ROW
    jmp print_center

draw_screen:
    mov r0, LIGHT_GREY
    call con_color
    call con_clear
    mov r0, s_title
    mov r1, TITLE_ROW
    mov r2, YELLOW
    call print_center
    mov r0, s_subtitle
    mov r1, TITLE_ROW + 1
    mov r2, DARK_GREY
    call print_center
    call draw_grid
    call draw_board
    call draw_info
    mov r0, s_help
    mov r1, HELP_ROW
    mov r2, DARK_GREY
    jmp print_center

draw_grid:
    push r4
    mov r0, LIGHT_GREY
    call con_color
    mov r4, 0
.row:
    mov r0, BOARD_X
    mov r1, r4
    add r1, BOARD_Y
    mov r2, grid_cells
    cmp r4, 3
    jeq .line
    cmp r4, 7
    jne .print
.line:
    mov r2, grid_line
.print:
    call con_print_at
    inc r4
    cmp r4, 11
    jne .row
    pop r4
    ret

draw_board:
    push r4
    mov r4, 0
.cell:
    mov r0, r4
    call draw_cell
    inc r4
    cmp r4, 9
    jne .cell
    pop r4
    ret

draw_cell:
    push r4
    push r5
    mov r4, r0
    mov r5, 0
    call in_win_line
    test r0, r0
    jz .no_win
    mov r5, WIN_BG
    jmp .origin
.no_win:
    mov r0, byte [show_cursor]
    test r0, r0
    jz .origin
    cmp r4, byte [cursor]
    jne .origin
    mov r0, byte [blink]
    test r0, r0
    jz .origin
    mov r5, CURSOR_BG
.origin:
    mov r0, r4
    mod r0, 3
    mul r0, 6
    add r0, BOARD_X
    mov r1, r4
    div r1, 3
    mul r1, 4
    add r1, BOARD_Y
    mul r1, SCREEN_COLS
    add r1, r0
    push r1
    mov r0, r5
    or r0, LIGHT_GREY
    mov r2, 3
.fill_row:
    mov r3, 5
.fill_col:
    mov byte [r1 + TEXT_BASE], ' '
    mov byte [r1 + ATTR_BASE], r0
    inc r1
    dec r3
    jnz .fill_col
    add r1, SCREEN_COLS - 5
    dec r2
    jnz .fill_row
    pop r1
    mov r2, byte [r4 + board]
    test r2, r2
    jz .hint
    mov r0, glyph_x
    mov r3, ATTR_X
    cmp r2, PLAYER
    jeq .glyph
    mov r0, glyph_o
    mov r3, ATTR_O
.glyph:
    or r3, r5
    add r1, 1
    mov r2, 3
.glyph_row:
    mov r4, 3
.glyph_col:
    mov r5, byte [r0]
    mov byte [r1 + TEXT_BASE], r5
    mov byte [r1 + ATTR_BASE], r3
    inc r0
    inc r1
    dec r4
    jnz .glyph_col
    add r1, SCREEN_COLS - 3
    dec r2
    jnz .glyph_row
    jmp .out
.hint:
    mov r0, r4
    add r0, '1'
    mov byte [r1 + TEXT_BASE], r0
    or r5, DARK_GREY
    mov byte [r1 + ATTR_BASE], r5
.out:
    pop r5
    pop r4
    ret

draw_info:
    mov r0, SCORE_ROW
    call clear_row
    mov r0, ATTR_X
    call con_color
    mov r0, 22
    mov r1, SCORE_ROW
    mov r2, s_you
    call con_print_at
    mov r0, [wins]
    call con_putu
    mov r0, ATTR_O
    call con_color
    mov r0, 35
    mov r1, SCORE_ROW
    mov r2, s_computer
    call con_print_at
    mov r0, [losses]
    call con_putu
    mov r0, LIGHT_GREY
    call con_color
    mov r0, 52
    mov r1, SCORE_ROW
    mov r2, s_draws
    call con_print_at
    mov r0, [draws]
    call con_putu
    mov r1, byte [difficulty]
    dec r1
    shl r1, 1
    mov r0, [r1 + level_names]
    mov r1, LEVEL_ROW
    mov r2, WHITE
    jmp print_center

draw_ai_stats:
    mov r0, STATS_ROW
    call clear_row
    mov r0, byte [difficulty]
    cmp r0, HARD
    jne .done
    mov r0, [ai_nodes]
    test r0, r0
    jz .done
    mov r0, DARK_GREY
    call con_color
    mov r0, 18
    mov r1, STATS_ROW
    mov r2, s_searched
    call con_print_at
    mov r0, [ai_nodes]
    call con_putu
    mov r0, s_positions
    call con_puts
    mov r0, s_expect_draw
    mov r1, [ai_score]
    test r1, r1
    jz .print
    mov r0, s_expect_win
    jpl .print
    mov r0, s_expect_loss
.print:
    call con_puts
.done:
    ret

grid_cells: .asciz "     |     |     "
grid_line: .asciz "-----+-----+-----"

s_title: .asciz "T I C - T A C - T O E"
s_subtitle: .asciz "written in A7 assembly, running on the A7-16 CPU"
s_help: .asciz "1-9 or arrows + enter: move    D: difficulty    R: restart    Q: quit"
s_you: .asciz "You  "
s_computer: .asciz "Computer  "
s_draws: .asciz "Draws  "
s_searched: .asciz "last search: "
s_positions: .asciz " positions, computer expects "
s_expect_win: .asciz "to win"
s_expect_draw: .asciz "a draw"
s_expect_loss: .asciz "to lose"

level_names: .dw s_easy, s_medium, s_hard
s_easy: .asciz "Difficulty: easy (random moves)"
s_medium: .asciz "Difficulty: medium (win, block, centre, corners)"
s_hard: .asciz "Difficulty: hard (minimax with alpha-beta pruning)"

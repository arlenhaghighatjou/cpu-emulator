.include "lib/hw.inc"

TICK_PERIOD = 20000
BLINK_TICKS = 25
ACT_MOVED = 0
ACT_RESTART = 1
ACT_QUIT = 2

.org VEC_TIMER * 2
.dw timer_isr
.org VEC_KEYBOARD * 2
.dw kbd_isr

.org 0x100
.entry start

start:
    mov r0, 0
    out DISPLAY_CTRL, r0
    call kbd_init
    mov r0, TICK_PERIOD & 0xFF
    out TIMER_RELOAD_L, r0
    mov r0, TICK_PERIOD >> 8
    out TIMER_RELOAD_H, r0
    mov r0, TIMER_ENABLE | TIMER_PERIODIC | TIMER_IRQ
    out TIMER_CTRL, r0
    sti

new_round:
    call board_clear
    mov byte [cursor], 4
    mov byte [show_cursor], 0
    mov word [ai_nodes], 0
    mov r0, byte [starter]
    mov byte [turn], r0
    call draw_screen

round:
    mov r0, byte [turn]
    cmp r0, COMPUTER
    jeq .computer
    call player_turn
    cmp r0, ACT_RESTART
    jeq new_round
    cmp r0, ACT_QUIT
    jeq quit
    jmp .judge
.computer:
    mov r0, s_thinking
    mov r1, ATTR_O
    call set_status
    call ai_move
    mov byte [r0 + board], COMPUTER
    call draw_board
    call draw_ai_stats
.judge:
    call board_winner
    test r0, r0
    jnz round_over
    mov r0, byte [turn]
    xor r0, PLAYER ^ COMPUTER
    mov byte [turn], r0
    jmp round

round_over:
    push r0
    call draw_board
    pop r0
    cmp r0, PLAYER
    jne .not_player
    mov r1, [wins]
    inc r1
    mov [wins], r1
    mov r0, s_you_win
    mov r1, LIGHT_GREEN
    jmp .announce
.not_player:
    cmp r0, COMPUTER
    jne .draw
    mov r1, [losses]
    inc r1
    mov [losses], r1
    mov r0, s_computer_wins
    mov r1, LIGHT_RED
    jmp .announce
.draw:
    mov r1, [draws]
    inc r1
    mov [draws], r1
    mov r0, s_draw
    mov r1, YELLOW
.announce:
    call set_status
    call draw_info
    mov r0, s_again
    mov r1, PROMPT_ROW
    mov r2, WHITE
    call print_center
    mov r0, byte [starter]
    xor r0, PLAYER ^ COMPUTER
    mov byte [starter], r0
.wait:
    call key_event
    test r0, r0
    jz .wait
    call lower
    cmp r0, 'r'
    jeq new_round
    cmp r0, KEY_ENTER
    jeq new_round
    cmp r0, ' '
    jeq new_round
    cmp r0, 'q'
    jeq quit
    cmp r0, 'd'
    jne .wait
    call next_difficulty
    jmp .wait

quit:
    mov r0, PROMPT_ROW
    call clear_row
    mov r0, s_bye
    mov r1, WHITE
    call set_status
    mov r0, 0
    out TIMER_CTRL, r0
    cli
    halt

player_turn:
    mov r0, s_your_move
    mov r1, ATTR_X
    call set_status
    mov byte [show_cursor], 1
    mov byte [blink], 1
    mov r0, byte [cursor]
    call draw_cell
.loop:
    call key_event
    test r0, r0
    jnz .key
    mov r0, byte [cursor]
    call draw_cell
    jmp .loop
.key:
    call lower
    mov r1, byte [cursor]
    cmp r0, 'q'
    jeq .quit
    cmp r0, 'r'
    jeq .restart
    cmp r0, 'd'
    jeq .difficulty
    cmp r0, KEY_ENTER
    jeq .select
    cmp r0, ' '
    jeq .select
    cmp r0, KEY_UP
    jeq .up
    cmp r0, KEY_DOWN
    jeq .down
    cmp r0, KEY_LEFT
    jeq .left
    cmp r0, KEY_RIGHT
    jeq .right
    cmp r0, '1'
    jlo .loop
    cmp r0, '9'
    jhi .loop
    sub r0, '1'
    jmp .place
.select:
    mov r0, r1
.place:
    mov r2, byte [r0 + board]
    test r2, r2
    jnz .taken
    mov byte [r0 + board], PLAYER
    mov byte [show_cursor], 0
    push r0
    mov byte [cursor], r0
    mov r0, r1
    call draw_cell
    pop r0
    call draw_cell
    mov r0, ACT_MOVED
    ret
.taken:
    mov r0, s_taken
    mov r1, YELLOW
    call set_status
    jmp .loop
.up:
    cmp r1, 3
    jlo .loop
    sub r1, 3
    jmp .move_cursor
.down:
    cmp r1, 6
    jhs .loop
    add r1, 3
    jmp .move_cursor
.left:
    mov r2, r1
    mod r2, 3
    jz .loop
    dec r1
    jmp .move_cursor
.right:
    mov r2, r1
    mod r2, 3
    cmp r2, 2
    jeq .loop
    inc r1
.move_cursor:
    mov r0, byte [cursor]
    mov byte [cursor], r1
    call draw_cell
    mov byte [blink], 1
    mov r0, byte [cursor]
    call draw_cell
    jmp .loop
.difficulty:
    call next_difficulty
    jmp .loop
.restart:
    mov byte [show_cursor], 0
    mov r0, ACT_RESTART
    ret
.quit:
    mov byte [show_cursor], 0
    mov r0, ACT_QUIT
    ret

next_difficulty:
    mov r0, byte [difficulty]
    mod r0, HARD
    inc r0
    mov byte [difficulty], r0
    call draw_ai_stats
    jmp draw_info

lower:
    cmp r0, 'A'
    jlo .done
    cmp r0, 'Z'
    jhi .done
    or r0, 0x20
.done:
    ret

timer_isr:
    push r0
    mov r0, byte [ticks]
    inc r0
    cmp r0, BLINK_TICKS
    jlo .store
    mov r0, byte [blink]
    xor r0, 1
    mov byte [blink], r0
    mov byte [kb_event], 1
    mov r0, 0
.store:
    mov byte [ticks], r0
    pop r0
    iret

turn: .db PLAYER
starter: .db PLAYER
ticks: .db 0

s_your_move: .asciz "Your move, you are X"
s_thinking: .asciz "Computer is thinking..."
s_taken: .asciz "That square is already taken"
s_you_win: .asciz "You win!"
s_computer_wins: .asciz "Computer wins!"
s_draw: .asciz "It's a draw"
s_again: .asciz "Press enter or R to play again, Q to quit"
s_bye: .asciz "Thanks for playing"

.include "tictactoe/screen.asm"
.include "lib/keys.asm"
.include "lib/std.asm"

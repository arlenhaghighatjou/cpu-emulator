.include "lib/hw.inc"

EMPTY = 0
PLAYER = 1
COMPUTER = 2
DRAW = 3
NO_CELL = 0xFF
NO_LINE = 0xFF

board: .ds 9
win_line: .db NO_LINE

lines:
    .db 0, 1, 2
    .db 3, 4, 5
    .db 6, 7, 8
    .db 0, 3, 6
    .db 1, 4, 7
    .db 2, 5, 8
    .db 0, 4, 8
    .db 2, 4, 6

cell_lines:
    .db 0, 3, 6, NO_LINE, NO_LINE
    .db 0, 4, NO_LINE, NO_LINE, NO_LINE
    .db 0, 5, 7, NO_LINE, NO_LINE
    .db 1, 3, NO_LINE, NO_LINE, NO_LINE
    .db 1, 4, 6, 7, NO_LINE
    .db 1, 5, NO_LINE, NO_LINE, NO_LINE
    .db 2, 3, 7, NO_LINE, NO_LINE
    .db 2, 4, NO_LINE, NO_LINE, NO_LINE
    .db 2, 5, 6, NO_LINE, NO_LINE

board_clear:
    mov r0, board
    mov r1, EMPTY
    mov r2, 9
    call mem_set
    mov byte [win_line], NO_LINE
    ret

board_winner:
    push r4
    push r5
    mov byte [win_line], NO_LINE
    mov r4, 0
    mov r5, 0
.line:
    mov r1, byte [r4 + lines]
    mov r0, byte [r1 + board]
    test r0, r0
    jz .next
    mov r1, byte [r4 + lines + 1]
    cmp r0, byte [r1 + board]
    jne .next
    mov r1, byte [r4 + lines + 2]
    cmp r0, byte [r1 + board]
    jne .next
    mov byte [win_line], r5
    jmp .out
.next:
    add r4, 3
    inc r5
    cmp r5, 8
    jne .line
    mov r1, 0
.full:
    mov r0, byte [r1 + board]
    test r0, r0
    jz .out
    inc r1
    cmp r1, 9
    jne .full
    mov r0, DRAW
.out:
    pop r5
    pop r4
    ret

wins_through:
    push r4
    mov r4, r0
    mul r4, 5
.line:
    mov r2, byte [r4 + cell_lines]
    cmp r2, NO_LINE
    jeq .no
    mul r2, 3
    mov r3, byte [r2 + lines]
    cmp r1, byte [r3 + board]
    jne .next
    mov r3, byte [r2 + lines + 1]
    cmp r1, byte [r3 + board]
    jne .next
    mov r3, byte [r2 + lines + 2]
    cmp r1, byte [r3 + board]
    jne .next
    mov r0, 1
    pop r4
    ret
.next:
    inc r4
    jmp .line
.no:
    mov r0, 0
    pop r4
    ret

count_empty:
    mov r0, 0
    mov r1, 0
.scan:
    mov r2, byte [r1 + board]
    test r2, r2
    jnz .taken
    inc r0
.taken:
    inc r1
    cmp r1, 9
    jne .scan
    ret

in_win_line:
    mov r1, byte [win_line]
    cmp r1, NO_LINE
    jeq .no
    mul r1, 3
    cmp r0, byte [r1 + lines]
    jeq .yes
    cmp r0, byte [r1 + lines + 1]
    jeq .yes
    cmp r0, byte [r1 + lines + 2]
    jeq .yes
.no:
    mov r0, 0
    ret
.yes:
    mov r0, 1
    ret

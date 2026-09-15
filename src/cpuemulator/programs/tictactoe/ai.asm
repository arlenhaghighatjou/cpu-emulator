.include "lib/hw.inc"
.include "tictactoe/board.asm"

EASY = 1
MEDIUM = 2
HARD = 3
WIN_SCORE = 10
INFINITY = 100

difficulty: .db HARD
ai_nodes: .dw 0
ai_score: .dw 0
ai_best_cell: .db NO_CELL
search_empty: .db 0

preference: .db 4, 0, 2, 6, 8, 1, 3, 5, 7

ai_move:
    mov word [ai_nodes], 0
    mov r0, byte [difficulty]
    cmp r0, EASY
    jeq ai_random
    cmp r0, MEDIUM
    jeq ai_rules
    call count_empty
    cmp r0, 8
    jhs ai_rules
    jmp ai_search

ai_random:
    call rand
    mod r0, 9
.probe:
    mov r1, byte [r0 + board]
    test r1, r1
    jz .done
    inc r0
    cmp r0, 9
    jne .probe
    mov r0, 0
    jmp .probe
.done:
    ret

ai_rules:
    mov r0, COMPUTER
    call find_winning
    cmp r0, NO_CELL
    jne .done
    mov r0, PLAYER
    call find_winning
    cmp r0, NO_CELL
    jne .done
    mov r1, 0
.prefer:
    mov r0, byte [r1 + preference]
    mov r2, byte [r0 + board]
    test r2, r2
    jz .done
    inc r1
    cmp r1, 9
    jne .prefer
    mov r0, NO_CELL
.done:
    ret

find_winning:
    push r4
    push r5
    mov r2, r0
    mov r4, 0
.line:
    mov r5, 0
    mov r3, NO_CELL
    mov r1, byte [r4 + lines]
    call .probe
    mov r1, byte [r4 + lines + 1]
    call .probe
    mov r1, byte [r4 + lines + 2]
    call .probe
    cmp r5, 2
    jne .next
    cmp r3, NO_CELL
    jeq .next
    mov r0, r3
    jmp .out
.next:
    add r4, 3
    cmp r4, 24
    jne .line
    mov r0, NO_CELL
.out:
    pop r5
    pop r4
    ret
.probe:
    mov r0, byte [r1 + board]
    cmp r0, r2
    jne .other
    inc r5
    ret
.other:
    test r0, r0
    jnz .blocked
    mov r3, r1
    ret
.blocked:
    mov r5, -8
    ret

ai_search:
    call count_empty
    mov byte [search_empty], r0
    mov byte [ai_best_cell], NO_CELL
    mov r0, COMPUTER
    mov r1, -INFINITY
    mov r2, INFINITY
    mov r3, 1
    call negamax
    mov [ai_score], r0
    mov r0, byte [ai_best_cell]
    ret

negamax:
    push fp
    mov fp, sp
    push r4
    push r5
    sub sp, 8
    mov r4, r0
    mov [fp - 6], r1
    mov [fp - 8], r2
    mov [fp - 10], r3
    mov word [fp - 12], -INFINITY
    mov r0, [ai_nodes]
    inc r0
    jz .counted
    mov [ai_nodes], r0
.counted:
    mov r5, 0
.move:
    mov r1, byte [r5 + preference]
    mov r0, byte [r1 + board]
    test r0, r0
    jnz .next
    mov byte [r1 + board], r4
    push r1
    mov r0, r1
    mov r1, r4
    call wins_through
    test r0, r0
    jz .deeper
    mov r0, WIN_SCORE
    sub r0, [fp - 10]
    jmp .scored
.deeper:
    mov r0, byte [search_empty]
    cmp r0, [fp - 10]
    jne .recurse
    mov r0, 0
    jmp .scored
.recurse:
    mov r0, r4
    xor r0, PLAYER ^ COMPUTER
    mov r1, [fp - 8]
    neg r1
    mov r2, [fp - 6]
    neg r2
    mov r3, [fp - 10]
    inc r3
    call negamax
    neg r0
.scored:
    pop r1
    mov byte [r1 + board], EMPTY
    cmp r0, [fp - 12]
    jle .bounds
    mov [fp - 12], r0
    mov r2, [fp - 10]
    cmp r2, 1
    jne .bounds
    mov byte [ai_best_cell], r1
.bounds:
    mov r0, [fp - 12]
    cmp r0, [fp - 6]
    jle .cutoff
    mov [fp - 6], r0
.cutoff:
    mov r0, [fp - 6]
    cmp r0, [fp - 8]
    jge .done
.next:
    inc r5
    cmp r5, 9
    jne .move
.done:
    mov r0, [fp - 12]
    lea sp, [fp - 4]
    pop r5
    pop r4
    pop fp
    ret

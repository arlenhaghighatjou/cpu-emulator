start:
    mov r4, 1
    mov r5, 0
.count:
    mov r0, r4
    call ser_putu
    mov r0, ' '
    call ser_putc
    add r5, r4
    inc r4
    cmp r4, 10
    jls .count
    call ser_newline

    mov r0, s_sum
    call ser_puts
    mov r0, r5
    call ser_putu
    call ser_newline

    mov r4, 5
.down:
    mov r0, r4
    call ser_putu
    dec r4
    jnz .down
    call ser_newline
    halt

s_sum: .asciz "sum "

.include "lib/std.asm"

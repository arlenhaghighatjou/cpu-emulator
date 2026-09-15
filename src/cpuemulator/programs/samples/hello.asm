.include "lib/hw.inc"

start:
    mov r0, WHITE | BLUE << 4
    call con_color
    call con_clear

    mov r0, 33
    mov r1, 10
    mov r2, s_hello
    call con_print_at

    mov r0, YELLOW | BLUE << 4
    call con_color
    mov r0, 28
    mov r1, 12
    mov r2, s_sub
    call con_print_at

    mov r4, 0
.swatch:
    mov r0, r4
    shl r0, 4
    call con_color
    mov r0, r4
    shl r0, 1
    add r0, 24
    mov r1, 15
    call con_goto
    mov r0, ' '
    call con_putc
    mov r0, ' '
    call con_putc
    inc r4
    cmp r4, 16
    jne .swatch

    mov r0, CURSOR_VISIBLE
    out DISPLAY_CTRL, r0
    mov r0, s_hello
    call ser_puts
    call ser_newline
    halt

s_hello: .asciz "Hello, world!"
s_sub: .asciz "running on the A7-16 CPU"

.include "lib/std.asm"

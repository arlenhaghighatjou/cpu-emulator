start:
    mov r0, s_add
    call ser_puts
    mov r0, 1234
    add r0, 4321
    call print_line

    mov r0, s_sub
    call ser_puts
    mov r0, 1000
    sub r0, 1
    call print_line

    mov r0, s_mul
    call ser_puts
    mov r0, 250
    mul r0, 12
    call print_line

    mov r0, s_div
    call ser_puts
    mov r4, 50000
    mov r0, r4
    div r0, 7
    call ser_putu
    mov r0, s_rem
    call ser_puts
    mov r0, r4
    mod r0, 7
    call print_line

    mov r0, s_idiv
    call ser_puts
    mov r0, -100
    idiv r0, 7
    call print_signed

    mov r0, s_carry
    call ser_puts
    mov r0, 0xFFFF
    add r0, 1
    mov r0, s_no
    jnc .no_carry
    mov r0, s_yes
.no_carry:
    call ser_puts
    call ser_newline

    mov r0, s_overflow
    call ser_puts
    mov r0, 0x7FFF
    add r0, 1
    mov r0, s_no
    jvc .no_overflow
    mov r0, s_yes
.no_overflow:
    call ser_puts
    call ser_newline

    mov r0, s_bits
    call ser_puts
    mov r0, 0x00F0
    shl r0, 4
    or r0, 0x000F
    xor r0, 0x0FF0
    call print_line

    mov r0, s_rotate
    call ser_puts
    mov r0, 0x8001
    rol r0, 1
    call print_line

    mov r0, s_neg
    call ser_puts
    mov r0, 5
    neg r0
    call print_signed
    halt

print_line:
    call ser_putu
    jmp ser_newline

print_signed:
    test r0, r0
    jpl .positive
    push r0
    mov r0, '-'
    call ser_putc
    pop r0
    neg r0
.positive:
    jmp print_line

s_add: .asciz "add "
s_sub: .asciz "sub "
s_mul: .asciz "mul "
s_div: .asciz "div "
s_rem: .asciz " rem "
s_idiv: .asciz "idiv "
s_carry: .asciz "carry "
s_overflow: .asciz "overflow "
s_bits: .asciz "bits "
s_rotate: .asciz "rotate "
s_neg: .asciz "neg "
s_yes: .asciz "yes"
s_no: .asciz "no"

.include "lib/std.asm"

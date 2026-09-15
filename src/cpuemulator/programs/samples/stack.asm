start:
    mov r0, 8
    call fact
    mov r4, r0
    mov r0, s_fact
    call ser_puts
    mov r0, r4
    call print

    mov r0, 100
    call sum_to
    mov r4, r0
    mov r0, s_sum
    call ser_puts
    mov r0, r4
    call print

    push 1
    push 2
    push 3
    pop r1
    pop r2
    pop r3
    mul r1, 100
    mul r2, 10
    add r1, r2
    add r1, r3
    mov r4, r1
    mov r0, s_pop
    call ser_puts
    mov r0, r4
    call print

    stc
    pushf
    clc
    popf
    mov r4, s_lost
    jnc .report
    mov r4, s_kept
.report:
    mov r0, s_flags
    call ser_puts
    mov r0, r4
    call ser_puts
    call ser_newline

    mov r0, s_sp
    call ser_puts
    mov r0, sp
    call print
    halt

fact:
    push r4
    mov r4, r0
    cmp r0, 1
    jls .base
    dec r0
    call fact
    mul r0, r4
    jmp .out
.base:
    mov r0, 1
.out:
    pop r4
    ret

sum_to:
    push fp
    mov fp, sp
    sub sp, 2
    mov [fp - 2], r0
    test r0, r0
    jz .zero
    dec r0
    call sum_to
    add r0, [fp - 2]
    jmp .out
.zero:
    mov r0, 0
.out:
    mov sp, fp
    pop fp
    ret

print:
    call ser_putu
    jmp ser_newline

s_fact: .asciz "fact 8 = "
s_sum: .asciz "sum 100 = "
s_pop: .asciz "pop "
s_flags: .asciz "flags "
s_kept: .asciz "kept"
s_lost: .asciz "lost"
s_sp: .asciz "sp "

.include "lib/std.asm"

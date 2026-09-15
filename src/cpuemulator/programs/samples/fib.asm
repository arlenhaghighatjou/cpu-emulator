start:
    mov r4, 0
    mov r5, 1
.next:
    mov r0, r4
    call ser_putu
    call ser_newline
    mov r0, r4
    add r0, r5
    jc .done
    mov r4, r5
    mov r5, r0
    jmp .next
.done:
    mov r0, r5
    call ser_putu
    call ser_newline
    halt

.include "lib/std.asm"

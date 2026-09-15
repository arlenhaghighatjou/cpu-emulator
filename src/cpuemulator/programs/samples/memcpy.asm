COPY = 0x4000

start:
    mov r0, COPY
    mov r1, message
    mov r2, message_end - message
    call mem_copy
    mov r0, COPY
    call print

    mov r0, buffer + 2
    mov r1, buffer
    mov r2, 4
    call mem_copy
    mov r0, buffer
    call print

    mov r0, buffer + 1
    mov r1, buffer + 2
    mov r2, 4
    call mem_copy
    mov r0, buffer
    call print

    mov r0, stars
    mov r1, '*'
    mov r2, 5
    call mem_set
    mov r0, stars
    call print

    mov r0, message
    call str_len
    call ser_putu
    call ser_newline
    halt

print:
    call ser_puts
    jmp ser_newline

message: .asciz "memory copy works"
message_end:
buffer: .asciz "abcdef"
stars: .ds 6

.include "lib/std.asm"

.include "lib/hw.inc"

con_x: .db 0
con_y: .db 0
con_attr: .db LIGHT_GREY

con_color:
    mov byte [con_attr], r0
    ret

con_goto:
    mov byte [con_x], r0
    mov byte [con_y], r1
    jmp con_sync

con_sync:
    mov r0, byte [con_x]
    out DISPLAY_CURSOR_X, r0
    mov r0, byte [con_y]
    out DISPLAY_CURSOR_Y, r0
    ret

con_clear:
    push r4
    mov r4, 0
.fill:
    mov byte [r4 + TEXT_BASE], ' '
    mov r0, byte [con_attr]
    mov byte [r4 + ATTR_BASE], r0
    inc r4
    cmp r4, SCREEN_COLS * SCREEN_ROWS
    jne .fill
    mov byte [con_x], 0
    mov byte [con_y], 0
    call con_sync
    pop r4
    ret

con_putc:
    cmp r0, 10
    jeq .newline
    mov r1, byte [con_y]
    mul r1, SCREEN_COLS
    mov r2, byte [con_x]
    add r1, r2
    mov byte [r1 + TEXT_BASE], r0
    mov r2, byte [con_attr]
    mov byte [r1 + ATTR_BASE], r2
    mov r2, byte [con_x]
    inc r2
    mov byte [con_x], r2
    cmp r2, SCREEN_COLS
    jlo con_sync
.newline:
    mov byte [con_x], 0
    mov r2, byte [con_y]
    inc r2
    cmp r2, SCREEN_ROWS
    jlo .store
    call con_scroll
    mov r2, SCREEN_ROWS - 1
.store:
    mov byte [con_y], r2
    jmp con_sync

con_scroll:
    push r4
    mov r0, TEXT_BASE
    mov r1, TEXT_BASE + SCREEN_COLS
    mov r2, SCREEN_COLS * (SCREEN_ROWS - 1)
    call mem_copy
    mov r0, ATTR_BASE
    mov r1, ATTR_BASE + SCREEN_COLS
    mov r2, SCREEN_COLS * (SCREEN_ROWS - 1)
    call mem_copy
    mov r4, SCREEN_COLS * (SCREEN_ROWS - 1)
.clear:
    mov byte [r4 + TEXT_BASE], ' '
    mov r0, byte [con_attr]
    mov byte [r4 + ATTR_BASE], r0
    inc r4
    cmp r4, SCREEN_COLS * SCREEN_ROWS
    jne .clear
    pop r4
    ret

con_puts:
    push r4
    mov r4, r0
.next:
    mov r0, byte [r4]
    test r0, r0
    jz .done
    call con_putc
    inc r4
    jmp .next
.done:
    pop r4
    ret

con_print_at:
    push r2
    call con_goto
    pop r0
    jmp con_puts

con_putu:
    sub sp, 6
    mov r1, sp
    call utoa
    mov r0, sp
    call con_puts
    add sp, 6
    ret

con_puthex:
    push r4
    push r5
    mov r4, r0
    mov r5, 4
.digit:
    rol r4, 4
    mov r0, r4
    and r0, 0x0F
    mov r0, byte [r0 + hex_digits]
    call con_putc
    dec r5
    jnz .digit
    pop r5
    pop r4
    ret

hex_digits: .ascii "0123456789ABCDEF"

utoa:
    push r4
    push r5
    mov r4, r0
    mov r5, 0
.count:
    inc r5
    div r0, 10
    jnz .count
    mov r2, r1
    add r2, r5
    mov byte [r2], 0
.write:
    dec r2
    mov r3, r4
    mod r3, 10
    add r3, '0'
    mov byte [r2], r3
    div r4, 10
    jnz .write
    mov r0, r5
    pop r5
    pop r4
    ret

str_len:
    mov r1, r0
.scan:
    mov r2, byte [r1]
    test r2, r2
    jz .end
    inc r1
    jmp .scan
.end:
    sub r1, r0
    mov r0, r1
    ret

mem_copy:
    test r2, r2
    jz .done
    cmp r0, r1
    jhi .backward
.forward:
    mov r3, byte [r1]
    mov byte [r0], r3
    inc r0
    inc r1
    dec r2
    jnz .forward
    ret
.backward:
    add r0, r2
    add r1, r2
.back:
    dec r0
    dec r1
    mov r3, byte [r1]
    mov byte [r0], r3
    dec r2
    jnz .back
.done:
    ret

mem_set:
    test r2, r2
    jz .done
.fill:
    mov byte [r0], r1
    inc r0
    dec r2
    jnz .fill
.done:
    ret

ser_putc:
    out SERIAL_DATA, r0
    ret

ser_puts:
    mov r1, r0
.next:
    mov r0, byte [r1]
    test r0, r0
    jz .done
    out SERIAL_DATA, r0
    inc r1
    jmp .next
.done:
    ret

ser_putu:
    sub sp, 6
    mov r1, sp
    call utoa
    mov r0, sp
    call ser_puts
    add sp, 6
    ret

ser_newline:
    mov r0, 10
    out SERIAL_DATA, r0
    ret

key_wait:
    in r0, KBD_STATUS
    test r0, KBD_READY
    jz key_wait
    in r0, KBD_DATA
    ret

rand:
    in r0, RNG_DATA_L
    in r1, RNG_DATA_H
    shl r1, 8
    or r0, r1
    ret

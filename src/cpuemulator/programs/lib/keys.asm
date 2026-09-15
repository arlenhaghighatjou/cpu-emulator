.include "lib/hw.inc"

KB_MASK = 15

kb_head: .db 0
kb_tail: .db 0
kb_buffer: .ds KB_MASK + 1

kbd_init:
    mov byte [kb_head], 0
    mov byte [kb_tail], 0
    mov r0, KBD_IRQ
    out KBD_CTRL, r0
    ret

kbd_isr:
    push r0
    push r1
.drain:
    in r0, KBD_STATUS
    test r0, KBD_READY
    jz .done
    in r0, KBD_DATA
    mov r1, byte [kb_head]
    mov byte [r1 + kb_buffer], r0
    inc r1
    and r1, KB_MASK
    cmp r1, byte [kb_tail]
    jeq .drain
    mov byte [kb_head], r1
    jmp .drain
.done:
    pop r1
    pop r0
    iret

key_get:
    cli
    mov r1, byte [kb_tail]
    cmp r1, byte [kb_head]
    jne .take
    sti
    wait
    jmp key_get
.take:
    mov r0, byte [r1 + kb_buffer]
    inc r1
    and r1, KB_MASK
    mov byte [kb_tail], r1
    sti
    ret

key_poll:
    cli
    mov r0, 0
    mov r1, byte [kb_tail]
    cmp r1, byte [kb_head]
    jeq .done
    mov r0, byte [r1 + kb_buffer]
    inc r1
    and r1, KB_MASK
    mov byte [kb_tail], r1
.done:
    sti
    ret

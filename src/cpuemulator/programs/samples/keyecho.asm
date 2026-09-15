.include "lib/hw.inc"

.org VEC_KEYBOARD * 2
.dw kbd_isr

.org 0x100
.entry start

start:
    mov r0, LIGHT_GREEN
    call con_color
    call con_clear
    mov r0, s_prompt
    call con_puts
    mov r0, CURSOR_VISIBLE
    out DISPLAY_CTRL, r0
    call kbd_init
    sti
.loop:
    call key_get
    cmp r0, KEY_ESCAPE
    jeq .quit
    cmp r0, KEY_ENTER
    jne .echo
    mov r0, 10
.echo:
    push r0
    call con_putc
    pop r0
    call ser_putc
    jmp .loop
.quit:
    cli
    halt

s_prompt: .asciz "type something, escape quits\n"

.include "lib/keys.asm"
.include "lib/std.asm"

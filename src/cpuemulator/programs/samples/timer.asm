.include "lib/hw.inc"

PERIOD = 1000

.org VEC_TIMER * 2
.dw on_timer

.org 0x100
.entry start

start:
    mov r0, PERIOD & 0xFF
    out TIMER_RELOAD_L, r0
    mov r0, PERIOD >> 8
    out TIMER_RELOAD_H, r0
    mov r0, TIMER_ENABLE | TIMER_PERIODIC | TIMER_IRQ
    out TIMER_CTRL, r0
    sti
.loop:
    wait
    mov r0, [ticks]
    mod r0, 10
    jnz .loop
    mov r0, s_tick
    call ser_puts
    mov r0, [ticks]
    call ser_putu
    call ser_newline
    mov r0, [ticks]
    cmp r0, 50
    jlo .loop
    cli
    mov r0, 0
    out TIMER_CTRL, r0
    halt

on_timer:
    push r0
    mov r0, [ticks]
    inc r0
    mov [ticks], r0
    pop r0
    iret

ticks: .dw 0
s_tick: .asciz "tick "

.include "lib/std.asm"

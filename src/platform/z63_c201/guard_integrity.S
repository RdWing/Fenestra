/* Stateless guard-area CRC32 (IEEE) over the immutable core reservation.
 * Called only by generated guards, which save x16/x17 and the original LR.
 * All other registers and NZCV are preserved. No interrupt-mask change,
 * allocation, firmware call, core call, mutable latch or persistent write.
 * Parameters and the CRC table live beside this routine in copied stock text.
 * The linker forbids writable static storage in the checked core.
 * Return w16 == 0 for valid, nonzero for absent/corrupt. */
.text
.p2align 3
.global fx_guard_integrity
fx_guard_integrity:
    stp x9,x10,[sp,#-64]!
    stp x11,x12,[sp,#16]
    stp x13,x14,[sp,#32]
    mrs x9,nzcv
    str x9,[sp,#48]
    adr x9,fx_guard_parameters
    ldp x17,x10,[x9]
    ldur x12,[x10,#-8]
    ldr x13,[x9,#24]
    cmp x12,x13
    b.ne 2f
    ldr w11,[x9,#16]
    mov w16,#-1
    adr x14,fx_guard_crc_table
1:
    ldrb w12,[x17],#1
    eor w12,w12,w16
    and w12,w12,#255
    ldr w13,[x14,w12,uxtw #2]
    eor w16,w13,w16,lsr #8
    cmp x17,x10
    b.lo 1b
    mvn w16,w16
    eor w16,w16,w11
    b 3f
2:
    mov w16,#1
3:
    ldr x9,[sp,#48]
    msr nzcv,x9
    ldp x13,x14,[sp,#32]
    ldp x11,x12,[sp,#16]
    ldp x9,x10,[sp],#64
    ret
.p2align 3
.global fx_guard_parameters
fx_guard_parameters:
    .space 32
.global fx_guard_crc_table
fx_guard_crc_table:

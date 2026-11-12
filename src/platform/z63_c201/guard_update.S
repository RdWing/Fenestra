/* Copied with stock W3. No optional-core call, heap, filesystem or NOR write.
 * Admission and activation compete on one retained RAM word: 0 = clean,
 * 1 = extension session, 2 = updater session. Only a cold text copy clears it.
 * A denied start returns stock's synchronous refusal (2), not pending (0/1).
 * The two API tail branches preserve their original arguments and return LR. */
.text
.p2align 3
.global fx_update_guard_one
fx_update_guard_one:
    stp x16,x17,[sp,#-32]!
    str x30,[sp,#16]
    bl fx_update_claim
    cbnz w16,fx_update_refuse
    ldr x30,[sp,#16]
    ldp x16,x17,[sp],#32
.global fx_update_stock_one
fx_update_stock_one:
    .inst 0
.global fx_update_guard_two
fx_update_guard_two:
    stp x16,x17,[sp,#-32]!
    str x30,[sp,#16]
    bl fx_update_claim
    cbnz w16,fx_update_refuse
    ldr x30,[sp,#16]
    ldp x16,x17,[sp],#32
.global fx_update_stock_two
fx_update_stock_two:
    .inst 0
fx_update_refuse:
    ldr x30,[sp,#16]
    ldp x16,x17,[sp],#32
    mov w0,#2
    ret
fx_update_claim:
    stp x9,x10,[sp,#-16]!
    ldr x9,fx_update_latch
1:
    ldaxr w16,[x9]
    cbnz w16,2f
    mov w10,#2
    stlxr w17,w10,[x9]
    cbnz w17,1b
    mov w16,#0
    b 3f
2:
    clrex
    sub w16,w16,#2
3:
    dc cvac,x9
    dsb sy
    ldp x9,x10,[sp],#16
    ret
.p2align 3
.global fx_update_latch
fx_update_latch:
    .quad 0

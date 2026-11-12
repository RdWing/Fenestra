/* Dispatcher entry in the copied guard area, independent of optional code.
 * Event 20 runs the original dispatcher to completion FIRST. Only then may
 * validation admit optional late initialization. Other events use the normal
 * state-gated guard. Patch words are resolved by the host builder, not runtime.
 * No allocation, mutex, system-register change or persistent write here. */
.text
.global fx_boot_guard
fx_boot_guard:
    stp x16,x17,[sp,#-16]!
    ldr w16,[x0,#32]
    sub w16,w16,#20
    cbz w16,1f
    ldp x16,x17,[sp],#16
.global fx_boot_normal
fx_boot_normal:
    .inst 0
1:
    ldp x16,x17,[sp],#16
    stp x0,x1,[sp,#-48]!
    str x30,[sp,#16]
.global fx_boot_stock_call
fx_boot_stock_call:
    .inst 0
    str x0,[sp,#24]
    /* The optional initializer takes no arguments. Keep stock's returned
     * caller-scratch state intact when validation rejects the core. */
    nop
    stp x16,x17,[sp,#32]
    mov w16,#1
.global fx_boot_validate
fx_boot_validate:
    .inst 0
    cbnz w16,2f
.global fx_boot_optional
fx_boot_optional:
    .inst 0
2:
    ldr x0,[sp,#24]
    ldr x30,[sp,#16]
    ldp x16,x17,[sp,#32]
    add sp,sp,#48
    ret
.global fx_boot_original
fx_boot_original:
    .space 20

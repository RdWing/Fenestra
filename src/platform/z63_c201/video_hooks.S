.text
/* Interior hooks preserve all GPR, SIMD and floating-point control state. */
.macro save
 sub sp,sp,#688
 stp x0,x1,[sp,#0]
 stp x2,x3,[sp,#16]
 stp x4,x5,[sp,#32]
 stp x6,x7,[sp,#48]
 stp x8,x9,[sp,#64]
 stp x10,x11,[sp,#80]
 stp x12,x13,[sp,#96]
 stp x14,x15,[sp,#112]
 stp x16,x17,[sp,#128]
 str x18,[sp,#144]
 str x30,[sp,#152]
 mrs x16,nzcv
 str x16,[sp,#160]
 mrs x16,fpcr
 str w16,[sp,#168]
 mrs x16,fpsr
 str w16,[sp,#172]
 stp q0,q1,[sp,#176]
 stp q2,q3,[sp,#208]
 stp q4,q5,[sp,#240]
 stp q6,q7,[sp,#272]
 stp q8,q9,[sp,#304]
 stp q10,q11,[sp,#336]
 stp q12,q13,[sp,#368]
 stp q14,q15,[sp,#400]
 stp q16,q17,[sp,#432]
 stp q18,q19,[sp,#464]
 stp q20,q21,[sp,#496]
 stp q22,q23,[sp,#528]
 stp q24,q25,[sp,#560]
 stp q26,q27,[sp,#592]
 stp q28,q29,[sp,#624]
 stp q30,q31,[sp,#656]
.endm
.macro restore_regs
 ldp q0,q1,[sp,#176]
 ldp q2,q3,[sp,#208]
 ldp q4,q5,[sp,#240]
 ldp q6,q7,[sp,#272]
 ldp q8,q9,[sp,#304]
 ldp q10,q11,[sp,#336]
 ldp q12,q13,[sp,#368]
 ldp q14,q15,[sp,#400]
 ldp q16,q17,[sp,#432]
 ldp q18,q19,[sp,#464]
 ldp q20,q21,[sp,#496]
 ldp q22,q23,[sp,#528]
 ldp q24,q25,[sp,#560]
 ldp q26,q27,[sp,#592]
 ldp q28,q29,[sp,#624]
 ldp q30,q31,[sp,#656]
 ldr w16,[sp,#168]
 msr fpcr,x16
 ldr w16,[sp,#172]
 msr fpsr,x16
 ldr x16,[sp,#160]
 msr nzcv,x16
 ldp x0,x1,[sp,#0]
 ldp x2,x3,[sp,#16]
 ldp x4,x5,[sp,#32]
 ldp x6,x7,[sp,#48]
 ldp x8,x9,[sp,#64]
 ldp x10,x11,[sp,#80]
 ldp x12,x13,[sp,#96]
 ldp x14,x15,[sp,#112]
 ldp x16,x17,[sp,#128]
 ldr x18,[sp,#144]
 ldr x30,[sp,#152]
 add sp,sp,#688
.endm

.global fx_z63_video_type_hook
fx_z63_video_type_hook:
 save
 bl fx_z63_video_code
 cbz w0,1f
 sub w8,w0,#1
 cmp w8,#4
 b 2f
1:
 ldr x8,[sp,#64]
 ldr w8,[x8]
 cmp w8,#2
2:
 str x8,[sp,#64]
 mrs x16,nzcv
 str x16,[sp,#160]
 restore_regs
 str w9,[x10]
 b fx_z63_video_type_return
.global fx_z63_video_template_hook
fx_z63_video_template_hook:
 save
 bl fx_z63_video_template
 str x0,[sp,#8]
 restore_regs
 mov w2,#86
 b fx_z63_video_template_return
.global fx_z63_video_shoot_hook
fx_z63_video_shoot_hook:
 save
 bl fx_z63_video_shoot
 mov x21,x0
 restore_regs
 .include "z63_video_shoot_count.inc"
 b fx_z63_video_shoot_return
.global fx_z63_video_play_hook
fx_z63_video_play_hook:
 save
 bl fx_z63_video_code
 cbz w0,1f
 add x0,sp,#984
 bl fx_z63_video_play
 restore_regs
 b fx_z63_video_play_return
1:
 restore_regs
 b fx_z63_video_play_stock_original
.global fx_z63_video_parser_hook
fx_z63_video_parser_hook:
 save
 bl fx_z63_video_code
 cbz w0,2f
 ldr w0,[sp,#0]
 bl fx_z63_video_parse
 str x0,[sp,#64]
 restore_regs
 cbz w8,1f
 b fx_z63_video_parse_accept
1:
 b fx_z63_video_parse_reject
2:
 restore_regs
 .include "z63_video_parser_compare.inc"
 b.eq 3f
 b fx_z63_video_parse_reject
3:
 b fx_z63_video_parse_accept
/* The selector tail carries the selected row index in x8. */
.global fx_z63_h265_select_tail
fx_z63_h265_select_tail:
 mov x3,x8
 mov x4,x30
 b fx_z63_h265_copy
.include "z63_video_original.inc"

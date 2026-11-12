#include <stdint.h>
#include "z63_log_assets.h"

/* Resident sources only. The caller owns mode admission and job lifetime.
 * A null result means retain the original source. Selection is exactly 0/1;
 * a corrupt or future selection cannot silently enable a conversion. */
uintptr_t fx_z63_log_source(uint32_t part,uint32_t selected) {
    if(selected!=1u)return 0;
    switch(part) {
    case 0:return (uintptr_t)fx_z63_log_m1;
    case 1:return (uintptr_t)fx_z63_log_m2;
    case 2:return (uintptr_t)fx_z63_log_rgb;
    case 3:return (uintptr_t)fx_z63_log_nlg;
    case 4:return (uintptr_t)fx_z63_log_cpxs;
    default:return 0;
    }
}

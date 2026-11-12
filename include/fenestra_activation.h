#ifndef FENESTRA_ACTIVATION_H
#define FENESTRA_ACTIVATION_H
#include "fenestra.h"
#include <stdatomic.h>
/* RAM-only session arbitration. UPDATE is terminal for activation; MODIFIED
 * remains terminal for updates even after every feature has drained. */
enum { FX_ACT_CLEAN=0u, FX_ACT_MODIFIED=1u, FX_ACT_UPDATE=2u, FX_ACT_BOOTSTRAP=3u };
enum { FX_ACT_STOCK=0u, FX_ACT_VALIDATING, FX_ACT_ACTIVE, FX_ACT_DRAINING,
       FX_ACT_LATCHED, FX_ACT_FAULT };
typedef struct { uint32_t site,original,replacement; } FxActivationWord;
typedef struct {
    void *context;
    FxResult (*check)(void *,const FxActivationWord *);
    uint32_t (*read)(void *,const FxActivationWord *);
    FxResult (*exchange)(void *,const FxActivationWord *,uint32_t,uint32_t);
    FxResult (*sync)(void *,const FxActivationWord *);
} FxActivationMemory;
/* No native references are freed by these operations. The caller keeps the
 * feature entry gate closed until commit and closes it only after draining. */
FxResult fx_activation_claim(_Atomic uint32_t *,int resume);
FxResult fx_activation_record(const uint8_t *,uint32_t,const uint8_t[32]);
FxResult fx_activation_install(const FxActivationWord *,uint32_t,const FxActivationMemory *,int,uint64_t *);
FxResult fx_activation_restore(const FxActivationWord *,uint32_t,const FxActivationMemory *,uint64_t *);
#endif

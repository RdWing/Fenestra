#ifndef FX_Z63_ACTIVATION_H
#define FX_Z63_ACTIVATION_H
#include "fenestra_activation.h"
#include "fenestra_startup_files.h"
typedef struct {
    _Atomic uint32_t phase,error;
    uint64_t owned;
    uint32_t resume,wake_after_drain;
} FxZ63Activation;
void fx_z63_activation_init(FxZ63Activation *);
FxResult fx_z63_activation_admit(FxZ63Activation *,FxStartupFiles *);
FxResult fx_z63_activation_install(FxZ63Activation *);
FxResult fx_z63_activation_restore(FxZ63Activation *);
void fx_z63_activation_running(FxZ63Activation *,uint64_t);
void fx_z63_activation_retire(FxZ63Activation *,int);
void fx_z63_activation_cleaned(FxZ63Activation *,FxResult);
uint64_t fx_z63_activation_token(void);
int fx_z63_activation_updating(void);
int fx_z63_activation_update_requires_restart(void);
uint32_t fx_z63_activation_shell_enter(void);
void fx_z63_activation_shell_leave(uint32_t);
#endif

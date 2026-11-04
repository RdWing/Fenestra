#include "fenestra_native_sdk.h"
static uint32_t notifications;
static FxResult notify(void *context,uint32_t event) {
    (void)context;(void)event;
    return ++notifications==1u?FX_BUSY:FX_OK;
}
int fenestra_native_entry(const FxNativeBootstrap *api,FxNativeExports *exports) {
    if(!api || !exports)return FX_ARGUMENT;
    exports->purpose=FX_MODULE_SERVICE;exports->notify=notify;
    return FX_INTEGRITY;
}

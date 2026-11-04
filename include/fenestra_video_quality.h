#ifndef FENESTRA_VIDEO_QUALITY_H
#define FENESTRA_VIDEO_QUALITY_H
#include <stdint.h>
#include <stdatomic.h>
#include "fenestra_services.h"
/* camera.video.quality/v1: session-only, family-specific choices. A request
 * can remain pending until all native admission owners have reached idle. */
#define FX_VIDEO_QUALITY_ABI 1u
#define FX_VIDEO_QUALITY_PROVIDER "camera.video.quality"
#define FX_VIDEO_FAMILY_PRORES422 1u
enum { FX_VIDEO_QUALITY_QUERY, FX_VIDEO_QUALITY_STATUS, FX_VIDEO_QUALITY_SELECT };
enum { FX_VIDEO_STOCK, FX_VIDEO_HQ, FX_VIDEO_STANDARD, FX_VIDEO_LT, FX_VIDEO_PROXY };
enum { FX_VIDEO_QUALITY_SESSION_ONLY=1u, FX_VIDEO_QUALITY_EXPERIMENTAL=2u, FX_VIDEO_QUALITY_UNAVAILABLE=4u };
typedef struct {uint32_t abi,bytes,family,choices,flags,reserved;} FxVideoQualityInfo;
typedef struct {uint32_t abi,bytes,family,choice;} FxVideoQualitySelection;
typedef struct {
    uint32_t abi,bytes,family,requested,effective,ready,movie_active,capture_active;
    uint32_t pending,fault,transitions,reserved;
} FxVideoQualityStatus;
/* The caller serializes policy operations with the SAME fence used by native
 * entry wrappers. Only effective is read without that fence by codec hooks. */
typedef struct {
    _Atomic uint32_t effective;
    uint32_t requested,registered,active[2],retiring,transitions;
    _Atomic uint32_t fault;
    uint64_t owner;
} FxVideoQualityPolicy;
void fx_video_quality_init(FxVideoQualityPolicy *);
void fx_video_quality_commit(FxVideoQualityPolicy *,uint32_t native_idle);
FxResult fx_video_quality_select(FxVideoQualityPolicy *,uint64_t owner,uint32_t choice,uint32_t native_idle);
FxResult fx_video_quality_release(FxVideoQualityPolicy *,uint64_t owner,uint32_t native_idle);
void fx_video_quality_enter(FxVideoQualityPolicy *,uint32_t domain,uint32_t acknowledge,uint32_t native_idle);
void fx_video_quality_leave(FxVideoQualityPolicy *,uint32_t domain,uint32_t native_idle);
#endif

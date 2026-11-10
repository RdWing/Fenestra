#ifndef FENESTRA_VIDEO_COLOR_H
#define FENESTRA_VIDEO_COLOR_H
#include "fenestra_video_quality.h"
/* ABI 1 shares the copied quality request layout. No camera pointers cross it.
 * Nonstock choices remain unavailable until the complete target path is bound. */
#define FX_VIDEO_FAMILY_COLOR 2u
#define FX_VIDEO_FAMILY_RAW 3u
#define FX_VIDEO_COLOR_PROVIDER "camera.video.color"
#define FX_VIDEO_RAW_PROVIDER "camera.video.raw"
enum { FX_VIDEO_PATH_H265, FX_VIDEO_PATH_PRORES422, FX_VIDEO_PATH_NRAW,
       FX_VIDEO_PATH_PRORESRAW, FX_VIDEO_PATH_PROXY, FX_VIDEO_PATH_COUNT };
enum { FX_VIDEO_REASON_NONE, FX_VIDEO_REASON_COLOR_JOIN,
       FX_VIDEO_REASON_WRITER_JOIN, FX_VIDEO_REASON_EI_JOIN };
/* Copied QUERY_PATH response, selected by the request's path index. */
#define FX_VIDEO_QUERY_PATH 4u
typedef struct {
    uint32_t abi,bytes,path,supported,reason,calibration,base_iso,ei_available;
} FxVideoPathInfo;
#endif

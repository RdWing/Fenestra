#ifndef FENESTRA_VIDEO_SETTINGS_H
#define FENESTRA_VIDEO_SETTINGS_H
#include <stdint.h>
/* C2.01 shared movie-word format. The ordinary low byte belongs to Nikon. */
int fx_h265_settings_read(uint32_t word, uint32_t *tier);
int fx_h265_settings_write(uint32_t word, uint32_t tier, uint32_t *replacement);
#endif

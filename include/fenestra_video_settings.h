#ifndef FENESTRA_VIDEO_SETTINGS_H
#define FENESTRA_VIDEO_SETTINGS_H
#include <stdint.h>
/* C2.01 shared movie-word format. The ordinary low byte belongs to Nikon. */
int fx_h265_settings_read(uint32_t word, uint32_t *tier);
int fx_h265_settings_write(uint32_t word, uint32_t tier, uint32_t *replacement);
/* Stored grades: HQ=0, Standard=1, LT=2, Proxy=3.
 * These are not the app choices, which also have a distinct Stock alias. */
int fx_prores_settings_read(uint32_t word, uint32_t *grade);
int fx_prores_settings_write(uint32_t word, uint32_t grade, uint32_t *replacement);
#endif

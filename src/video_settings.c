#include "fenestra_video_settings.h"

static uint32_t crc8(uint32_t bytes) {
    uint32_t crc = 0;
    for (uint32_t index = 0; index < 2; ++index) {
        crc ^= (bytes >> (8u * index)) & 255u;
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = ((crc << 1) ^ ((crc & 128u) ? 7u : 0u)) & 255u;
    }
    return crc;
}

static int payload(uint32_t word, uint32_t *value) {
    uint32_t high = word >> 8;
    if (!high) {
        *value = 0xa000u;
        return 1;
    }
    uint32_t legacy = (word >> 16) & 255u;
    if ((high & 255u) == 0x63u && legacy < 4u &&
        (word >> 24) == crc8(0x63u | (legacy << 8))) {
        *value = 0xa000u | legacy;
        return 1;
    }
    uint32_t record = high & 65535u;
    uint32_t version = record & 0xe000u;
    if ((version != 0xa000u && version != 0xc000u) ||
        (word >> 24) != crc8(record) || ((record >> 2) & 7u) > 4u ||
        ((record >> 8) & 3u) > 2u)
        return 0;
    *value = record;
    return 1;
}

int fx_h265_settings_read(uint32_t word, uint32_t *tier) {
    uint32_t record;
    if (!tier || !payload(word, &record)) return 0;
    *tier = (record >> 2) & 7u;
    return 1;
}

int fx_h265_settings_write(uint32_t word, uint32_t tier, uint32_t *replacement) {
    uint32_t record;
    if (!replacement || tier > 4u || (word & 255u) > 1u || !payload(word, &record))
        return 0;
    record = (record & ~0x1cu) | (tier << 2);
    *replacement = (word & 255u) | (record << 8) | (crc8(record) << 24);
    return 1;
}

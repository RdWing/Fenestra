"""Desktop Kaiji pixel arithmetic. Camera equivalence remains unproved."""


def round_shift(value, bits):
    return (value + (1 << (bits - 1)) - (value < 0)) >> bits


def m1_pixel(rgb, matrix, negative_clip=0):
    if len(rgb) != 3 or len(matrix) != 9:
        raise ValueError('supply three components and nine coefficients')
    if not all(0 <= x <= 65535 for x in rgb):
        raise ValueError('input components must fit unsigned 16 bits')
    if not all(-4096 <= x <= 4095 for x in matrix):
        raise ValueError('M1 coefficients must fit signed 13 bits')
    if not 0 <= negative_clip <= 65535:
        raise ValueError('negative clip must fit unsigned 16 bits')
    return tuple(max(-negative_clip, min(65535, round_shift(sum(
        round_shift(matrix[3 * row + col] * rgb[col], 9)
        for col in range(3)), 1))) for row in range(3))


def paired_curves(rgb, tables, alpha=256, negative_mode=0, offset=0, clip=0):
    if len(rgb) != 3 or len(tables) != 6 or any(len(t) != 65536 for t in tables):
        raise ValueError('supply three components and six expanded tables')
    if not all(-65535 <= x <= 65535 for x in rgb):
        raise ValueError('M1 output exceeds the lookup domain')
    if not 0 <= alpha <= 256 or negative_mode not in (0, 1):
        raise ValueError('unsupported curve control')
    if not 0 <= offset <= 32767 or not 0 <= clip <= 32767:
        raise ValueError('unsupported negative curve range')
    result = []
    for channel, value in enumerate(rgb):
        first, second = (tables[2 * channel + i][abs(value)] for i in (0, 1))
        if not 0 <= first <= 32767 or not 0 <= second <= 32767:
            raise ValueError('curve samples must fit unsigned 15 bits')
        mapped = max(0, min(32767, (alpha * first + (256 - alpha) * second) >> 8))
        if value < 0:
            # Mode zero narrows the signed M1 result before adding the offset.
            narrowed = ((value + 32768) & 65535) - 32768
            mapped = (-mapped if negative_mode else narrowed) + offset
        result.append(max(-clip, min(32767, mapped)))
    return tuple(result)

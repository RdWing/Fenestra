"""C2.01 coefficient arithmetic and transport. No hardware pixel model."""
import struct


def signed(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def trunc_div(value, divisor):
    return (1 if value >= 0 else -1) * (abs(value) // divisor)


def matrix_product(left, right, divisor):
    """Model 0x41135B2C, including s32 accumulation and s16 narrowing."""
    if len(left) != 9 or len(right) != 9:
        raise ValueError('expected nine coefficients in each matrix')
    if any(type(v) is not int or not -32768 <= v <= 32767 for v in (*left, *right)):
        raise ValueError('coefficient outside signed 16-bit range')
    if type(divisor) is not int or not 0 <= divisor <= 0x7fffffff:
        raise ValueError('divisor outside the checked nonnegative domain')
    out = []
    for row in range(3):
        for col in range(3):
            total = signed(sum(left[row*3+k] * right[k*3+col] for k in range(3)), 32)
            if divisor == 0:
                value = 0
            elif signed(total + 0x40000000, 32) < 0:
                value = trunc_div(total, divisor)
            else:
                twice = trunc_div(signed(total * 2, 32), divisor)
                value = trunc_div(signed(twice + (1 if total >= 0 else -1), 32), 2)
            out.append(signed(value, 16))
    return out


def m1_registers(block):
    """Return the six words written by 0x40C10D94, in address order."""
    if len(block) != 20:
        raise ValueError('M1 block must contain 20 bytes')
    clip, *coefficients = struct.unpack('<10H', block)
    return [clip] + [(coefficients[k] & 8191) | ((coefficients[k+1] & 8191) << 16)
                     for k in range(0, 8, 2)] + [coefficients[8] & 8191]

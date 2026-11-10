"""Bounded offline inverse of the published Nikon RAW decoder F model.

Arithmetic reference: NikonFirmwarePatch a21fc8c04b6dd863439c4192d387b755633287f6,
tools/build_f_lut.py (XinmiaoZhao, GPL-3.0-only). This independent implementation
uses the published equation, not the project's LUT or implementation code.
Measured decoder controls belong to the calibration receipt. This module never
adds F to recorded pixels and does not infer a camera input basis from a label.
"""
import numpy as np


def inverse_pixels(values, *, minimum_peak=.01, maximum_derivative=8.,
                   branch_margin=.001):
    """Return linear candidates and a per-pixel admission mask.

    Rejected rows are NaN, so callers cannot accidentally average unchanged
    decoder output into inverse-domain samples. Invert before spatial or
    temporal averaging. The scale-free model does not identify the decoder's
    near-black activation threshold; minimum_peak is an analysis bound.
    """
    rgb = np.asarray(values, dtype=float)
    if rgb.ndim != 2 or rgb.shape[1] != 3 or not np.isfinite(rgb).all():
        raise ValueError('expected finite RGB rows')
    if (not np.isfinite([minimum_peak, maximum_derivative, branch_margin]).all()
            or minimum_peak <= 0 or maximum_derivative < 1
            or not 0 <= branch_margin < 1):
        raise ValueError('invalid inverse bounds')
    peak = rgb.max(axis=1)
    # Nonpositive peaks are rejected below. Do not divide their channels by
    # tiny: ordinary negative inputs would overflow before the rejection.
    ratio = rgb.min(axis=1) / np.where(peak > 0, peak, 1.)
    blue_distance = rgb[:, 2] - rgb[:, :2].max(axis=1)
    threshold = np.where(blue_distance > 0, .5, .05)
    admitted = ((peak > minimum_peak) & (ratio > 0)
                & ((np.abs(blue_distance) > peak * branch_margin) | (ratio >= .5)))
    mapped = admitted & (ratio < threshold)
    minimum = ratio.copy()
    minimum[mapped] = ((1 + threshold[mapped])
                       * (ratio[mapped] / threshold[mapped])
                       ** (threshold[mapped] / (1 + threshold[mapped]))) - 1
    derivative = np.ones(len(rgb))
    derivative[mapped] = ((minimum[mapped] + 1) * threshold[mapped]
                          / ((1 + threshold[mapped]) * ratio[mapped]))
    admitted &= derivative <= maximum_derivative
    mapped &= admitted
    output = np.full_like(rgb, np.nan)
    output[admitted] = rgb[admitted]
    # Rearranged about the fixed maximum channel to retain negative pre-F
    # channels. Clamping those channels would change the fitted gamut.
    factor = (1 - minimum[mapped]) / (1 - ratio[mapped])
    output[mapped] = (peak[mapped, None]
                      + (rgb[mapped] - peak[mapped, None]) * factor[:, None])
    return output, admitted

---
version: alpha
name: Fenestra native camera UI
description: Native camera menus for module controls and status.
omitted:
  - section: colors
    reason: The original firmware owns the native menu palette.
  - section: typography
    reason: The original firmware owns native fonts and text metrics.
  - section: rounded
    reason: The original firmware owns native control shapes.
  - section: spacing
    reason: The original firmware owns menu geometry and row spacing.
  - section: components
    reason: C UI contracts own the controls, without CSS tokens.
---

# Fenestra native camera UI

## Overview

Fenestra extends the camera's native menus. Photographers use the same buttons,
selection highlight, choice pages and Back routes as the original camera.
The ProRes page uses this product style. It adds no separate visual theme.

Module labels currently use English. Native strings use the firmware renderer.
This is not a claim of translated module content or Japanese localization.
Physical accessibility and touch behavior need separate device tests.

The runtime remains the style owner. This file explains that ownership. It
exports no tokens and defines no competing palette.

## Colors

The native renderer supplies backgrounds, text, focus and disabled colors.
Modules express visible and enabled state through `FxUiControl.flags`.
The ProRes page explains unavailable selection with text as well as disabling it.

## Typography

The shared adapter copies bounded UTF-8 labels into owned UTF-16 text.
The native renderer supplies fonts and measurements. Keep labels short enough
for the native row. Do not embed fonts in a feature module.

## Layout

A module publishes a root PAGE and ordered controls. The shared adapter owns
native row geometry, choice pages and Back navigation. Update values in place
so a pending request does not move the controls.

## Components

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Select/Listbox | `src/native_ui.c` | `include/fenestra_platform.h` | Native choice page | Host UI tests and full-system choice controls |

The shared `src/ui_controls.inc` validates control state.
`src/native_ui.c` maps it to native menu controls.
`src/platform/z63_c201/ui.c` connects the Z63 profile.
The SDK demo supplies a sibling page and focus workflow.

One managed ProRes module calls the core video backend. The app's Quality row
shows the requested value. Effective reports the published value or pending/fault
state. Missing services disable selection and show a core requirement.
The optional Video recording row uses the same state and native choice page.
It follows Video quality (N-RAW), stays disabled outside ProRes and keeps the
native font and value alignment. The target adapter owns this placement.
A page close preserves the session choice. Stop disables native menu input
before core cleanup requests Stock. The module README defines admission and
retirement.

Use the camera's button navigation. Keep Back available. Do not simulate
successful selection while the provider or backend is unavailable.

# ProRes quality module

The experimental Z6III C2.01 feature needs one card module: `prores.wlm`.
It runs in managed EL0 and calls the core service `camera.video.quality`.
The C2.01 core owns the ROM hooks, native registration and recording fence.
The module contains no native camera addresses or firmware tables.

This local branch assumes [PR #6](https://github.com/WonderLantern/Fenestra/pull/6)
at `2bbea75282b7a56d6855a33b303b35ce6f3d23d1`. It does not require an upstream
merge. The earlier `prsnat.wlm` only forwarded requests to the same backend.
Remove that older wrapper from the emulator card when testing this branch.

## Build and start

Build a core with `fenestra.py build --target z63-c201 --experimental-video`
and the other required arguments. Build the module with LLVM on `PATH`:

```sh
python host/build_sdk_module.py modules/prores/module.c --id prores --target z63-c201 --required 0x390000 --native-stack-bytes 65536 --user-stack-bytes 65536 --output-dir build/prores-ui
```

1. Copy `prores.wlm` into `FENESTRA/` on an emulator card.
2. Start modules from the Fenestra menu.
3. Open Applications, then ProRes quality.

A core without the service shows “Requires updated core” and disables selection.
An older quality backend can still supply the app without the optional native
menu. The app requests menu attachment only when the backend advertises it.

## Native Video recording menu

After module activation, open the Video recording menu. “Video quality (ProRes)”
appears after “Video quality (N-RAW)”. The row is disabled for other formats.
Select ProRes 422 in the original Video file type menu to enable it.

The selector offers Stock, HQ, Standard, LT and Proxy. Stock restores the
original HQ path. Both the native selector and the app use the same backend
state. The app copies the current requested value when it polls status.
The native row shows the requested value, or “Waiting” during a pending change.
Back and closing either page preserve the session choice.

The target adapter owns the copied menu, callbacks and reserved text IDs.
The module supplies no native pointers. Menu attachment retains its owner and
binding token. Stop disables that attachment before requesting Stock.

## Ownership and stop

The backend restores the saved grade when the module attaches after boot.
Stored HQ grade zero restores as Stock; HQ remains a separate in-session alias. Selection claims the binding token.
Another binding receives BUSY until the owner releases it. A change becomes
effective only after both native worker registrations and retirement of tracked
jobs. Native admission must also report idle. The app's Effective row shows
the published choice, “Waiting for idle”, or “Needs restart”. A tracking fault
retains the last effective choice.

Select Stock to restore the original path. During shutdown, core resource
cleanup requests Stock and waits for native work. The core retains its hooks
and copied UI storage until reboot. Selections save through the original settings worker, sharing the transaction
guard with H.265. Failed or suppressed saves preserve the prior selection;
a valid reset or recall that supersedes the transaction takes precedence.
Shutdown restores runtime Stock without erasing the saved grade. The original Video file type menu
still selects the recording format.

This feature joins request admission, rate estimates, sample description,
shooting labels and playback recognition. It does not replace the encoder.
All local builds remain emulator-only `DO_NOT_FLASH` experiments.

## Tests and limits

```sh
python -B -m unittest discover -s tests -v
python -B host/verify_z63_video_hooks.py --application inputs/z63-original.bi --build build/video-core
python -B host/verify_z63_video_menu.py --build build/video-core
```

Host tests use the actual module and service routing with a substituted camera
backend. They cover missing services, optional menu support, owner exclusion,
BUSY retries, pending changes, native-to-app value changes and deferred Stock
cleanup. The independent SDK test also builds native packages for ZR, Z9 and
Z63 against synthetic APIs. That test qualifies the framework, not this
managed module's recording output.

Linked checks compare Stock register and stack effects, the playback-label
destination, rates, sample descriptions, shooting labels and playback consumers.
Selected helpers or the context getter are substitutes in these checks.

The full-system harness accepts `--video-test --module-count 1`.
`--video-menu-test` adds native menu controls and requires `--video-test`.
Video-format changes reach an unmodeled graphics command. The menu control
explicitly uses `gfx-skip-unmodelled=on` and records that model override.
The separate `--video-record-choice 0` through `4` controls observe native
requests up to the strict unmodeled CODEC stop. They explicitly skip separate
graphics gaps and report `recording_completed: false`. Restart the emulator
after that stop. These controls do not qualify encoded video, bitrate,
physical operation, update installation or failed-boot recovery.

Recording controls switch directly to Movie mode. The optional
`--video-prepare legacy-half` repeats the earlier still-half-press sequence.
Each run saves the prepared and requested movie screens. A native reset error
does not qualify recording admission.

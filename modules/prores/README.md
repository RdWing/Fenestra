# ProRes quality modules

The experimental Z6III C2.01 feature uses two card modules:

| File | Execution | Role |
| --- | --- | --- |
| `prores.wlm` | Managed EL0 | Owns the page and copied selection requests. |
| `prsnat.wlm` | Native resident | Publishes `camera.video.quality/v1` through `core.providers`. |

This local integration assumes [PR #6](https://github.com/WonderLantern/Fenestra/pull/6)
at `2bbea75282b7a56d6855a33b303b35ce6f3d23d1`. It does not require an upstream
merge. The native module uses the optional C2.01 backend in the core. That
backend still owns the ROM hooks, native registration and recording fence.
The card modules contain no native camera addresses or firmware tables.

## Build and start

Build a core with `fenestra.py build --target z63-c201 --experimental-video`
and the other required build arguments. Then build both modules with LLVM on
`PATH`:

```sh
python host/build_sdk_module.py modules/prores/module.c --id prores --target z63-c201 --required 0x310000 --native-stack-bytes 65536 --user-stack-bytes 65536 --output-dir build/prores-ui
python host/build_sdk_module.py modules/prores/native.c --native --id prsnat --target z63-c201 --required 0x290000 --output-dir build/prores-native
```

1. Copy both WLM files into `FENESTRA/` on an emulator card.
2. Start modules from the Fenestra menu.
3. Open Applications, then ProRes quality.

The UI can start before the provider. It shows “Load prsnat.wlm”, disables
selection and repeats discovery. An older core shows “Requires updated core”.
A core without the video backend shows “Requires video core”. The native
provider reports this last condition without a module fault.

## Ownership and stop

The provider starts at Stock on each boot. The first successful selection
claims the client owner and generation. Another client receives BUSY until
Stock becomes effective and a status request releases the claim. Read-only
query and status requests remain available to other clients.

A choice becomes effective only after both native worker registrations,
retirement of tracked jobs and admission by the native state. The Effective
row shows the published choice, “Waiting for idle”, or “Needs restart”. A
tracking fault retains the last effective choice.

Closing the page leaves both modules resident. Select Stock to restore the
original path. During shutdown, the provider stops new calls and waits for
active calls. Core resource cleanup then requests Stock and waits for native
work. Code and hooks remain resident until reboot. Choices apply to this
session. The modules write no preferences or camera settings.

The native Video file type menu still selects the recording format. This
feature joins ProRes 422 request admission, rate estimates, sample description,
shooting labels and playback recognition. It does not replace the encoder.
All local builds remain emulator-only `DO_NOT_FLASH` experiments.

## Tests and limits

```sh
python -B -m unittest discover -s tests -v
python -B host/verify_z63_video_hooks.py --application inputs/z63-original.bi --build build/video-core
```

Host tests use the real registry and module sources with a substituted camera
backend. They cover late discovery, owner exclusion, BUSY retries, unavailable
services, withdrawal and deferred Stock restoration. The standalone SDK test
builds native packages for ZR, Z9 and Z63 and executes them with synthetic APIs.

Linked checks compare Stock register and stack effects, the playback-label
destination, rates, sample descriptions, shooting labels and playback consumers.
Selected helpers or the context getter are substitutes in these checks.

The full-system harness accepts `--video-test --module-count 2` with its native
menu and UI controls. Manual startup and shutdown controls select every quality,
restore Stock, then leave Proxy active to check shutdown. They also require one
native start and acknowledged native stop.

The separate `--video-record-choice 0` through `4` controls observe native
requests up to the strict unmodeled CODEC stop. They explicitly skip separate
graphics gaps and report `recording_completed: false`. Restart the emulator
after that stop. These controls do not qualify encoded video, bitrate,
physical camera operation, update installation or failed-boot recovery.

Recording controls switch directly to Movie mode. The optional
`--video-prepare legacy-half` repeats the earlier still-half-press sequence.
Each run saves the prepared and requested movie screens. A native reset error
does not qualify recording admission.

# ProRes quality app

Experimental Z6III C2.01 app for the optional `camera.video.quality/v1`
provider. It selects Stock, HQ, Standard, LT or Proxy through a copied-message
interface. It contains no native addresses or firmware tables.

Build a core with `fenestra.py build --target z63-c201 --experimental-video`
and the other required build arguments. The ordinary core does not include
this provider. Then build the app with LLVM on `PATH`:

```sh
python host/build_sdk_module.py modules/prores/module.c --id prores --target z63-c201 --required 0x390000 --native-stack-bytes 65536 --user-stack-bytes 65536 --output-dir build/prores-app
```

Copy the resulting `prores.wlm` into `FENESTRA/` on an emulator card. Start
modules, open Applications, then ProRes quality. An older core shows
“Requires updated core” and disables selection.

The provider starts at Stock on every boot. A requested quality becomes
effective only after both native worker registrations are acknowledged,
all tracked jobs retire and native state permits publication. The Effective
row reports the published value or “Waiting for idle.” A tracking fault
reports “Needs restart” and retains the last effective choice to avoid
changing metadata during uncertain work.

Closing the page leaves the extension running. Select Stock to restore the
original path. Resource retirement requests Stock and waits for outstanding
work; it does not hot-unload the resident hooks. Choices are session only:
the app writes neither preference files nor camera settings storage.

The native Video file type setting still selects the recording format. This
app changes the ProRes 422 quality consumers together: request admission,
rate estimates, sample description, shooting label and playback recognition.
It does not replace the encoder. Menu and request-path tests do not qualify
completed Standard/LT/Proxy recording, actual bitrate, physical camera
operation or recovery. Local builds remain emulator-only `DO_NOT_FLASH`
experiments.
Attempting to record currently pauses the emulator at its unmodeled CODEC
operation; restart the emulator to continue.

## Validation

Run the host suite, then check the actual linked hooks and consumers against
the same original member used for the experimental core:

```sh
python -B -m unittest discover -s tests -v
python -B host/verify_z63_video_hooks.py --application inputs/z63-original.bi --build build/video-core
```

The instruction checks compare Stock register and stack effects, verify the
native playback-label destination, and exercise rate, sample-description,
shooting-label and playback consumers. They substitute selected helpers or the
retained-context getter; they do not exercise native task ownership.

The full-system harness accepts `--video-test` with its native menu/UI control.
With manual startup and shutdown controls, it selects every quality, restores
Stock, then leaves Proxy selected to check resource retirement at power-off.
The separate `--video-record-choice 0` through `4` controls observe native
recording requests up to the expected strict CODEC-model stop. Those controls
explicitly skip separately unmodeled graphics commands and report
`recording_completed: false`; a passing request control is not a completed
recording. Emulator, original components and disposable storage must be
supplied separately.

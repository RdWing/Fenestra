# H.265 bitrate app

This managed Z6III C2.01 app offers 100%, 60%, 45%, 30%, and 20% in the
Fenestra Applications menu and a Video bitrate (H.265) selector in the native
Video recording menu. It opens `camera.video.h265/v2` on a matching
experimental video core. Build the module with the Z63 SDK and an ID of
`h265`:

```sh
python host/build_sdk_module.py modules/h265/module.c --id h265 --target z63-c201 --bundle --required 0x390000 --native-stack-bytes 65536 --user-stack-bytes 65536 --output-dir build/h265-module
```

The choice is saved through the original camera settings worker. The service
accepts reduced tiers with H.265 8-bit or 10-bit selected, and refuses changes
while recording or another save is in flight. It publishes only an acknowledged,
successful save. Suppressed and failed saves roll back owned bytes; a valid
reset or recall that supersedes them wins. Shutdown restores the runtime tier
to 100%; the next module attachment restores the saved choice after native
settings loading. The ProRes and R3D NE choices retain their own state.

The shared settings codec preserves Nikon's low byte and unrelated fields in
valid v2/v3 records, and accepts the older ProRes record. Unknown or corrupt
records are refused. This emulator-tested record use is experimental; physical
retention and interrupted writes are not qualified.

The core calls the original row-copy routine and scales only the nominal rate
in an eligible H.265 row. The original selector, geometry, frame rate and GOP
fields stay in use. The linked check covers 42 eligible rows and 19 stock rows,
including AVC and retained 8K entries. Each of the five tiers is checked against
the original selector and encoder parameter builder. The displayed percentages
select a nominal target. File bitrate needs its own recording check.

Use `host/verify_z63_h265.py` with a pinned original EG and the linked core.
The harness runs the original selector with synthetic mode inputs and explicitly
substitutes the copy leaf, context, mutex and setting read. The full-system
`--video-test --h265-test` control checks the managed app and retirement with one
module on the card. Add `--video-menu-test` to exercise the native selector, its cancel and Back
paths, original sibling routes and app synchronization. `--export-snor` after
an acknowledged shutdown exports the modeled settings for a fresh-process
restart control; use `--h265-initial-tier` to assert the restored choice.

`--h265-record-tier` requires `--video-menu-test` and an explicitly supplied
`--video-properties` fixture. The recording control uses native H.265
10-bit by default (`--h265-depth 8` selects 8-bit) and Microphone off. It checks
fresh live view before REC, waits eight seconds by default, requests Stop and
requires native retirement before playback. `--h265-record-seconds` bounds the
dwell to 1–60 seconds; elapsed time is not proof of encoded duration. Audit
the stopped card and complete movie decode separately. A compatible emulator
may require the explicit `--dma-copy-zero-model` diagnostic to admit mode-zero
row copies during drain; the runner records that model choice. The functional codec
and pixels are substitutes; short silent clips cannot qualify sustained rate,
GOP behavior, sound or physical-camera operation. Other native quality icons
remain separate from recorded playback metadata.

The core captures an immutable type/tier/generation when the original native
recording request is copied. Encoder setup and the late recorded-class writer
read that snapshot. A repeated preparation preserves the first choice. Release
requires the observed original buffer clear, native idle and no tracked
callbacks; missing or conflicting ownership keeps the session retained.
`host/check_z63_recording.py` exercises original copy/clear/metadata instructions
with explicit mutex/state fixtures, including late preference changes and
failure cases. Full-system acceptance is separate from these linked tests.

Provider version 2 is required before attachment so the module cannot restore
a tier on an older core without the recording contract. The request structure
ABI remains 1 and the package format remains WLM v4.

The current core defers context construction until the original startup
completion handler returns. Existing native workers are joined only after
publication: their task identity and exact dispatcher-event wait are checked
under the recording fence, or their callbacks acknowledge the new context.
Unknown, active or mismatched states keep the choice pending or return BUSY;
they do not trigger a persistence request merely to force readiness. This
late join has local instruction/model controls, not physical-camera timing
or complete asynchronous writer-lifetime qualification.

The local recording controls also cover early Stop, native capacity refusal,
active card-detect loss/reinsertion and a one-shot NVMe write error through
`--h265-failure`. Recording cleanup, module quiescence and journal cleanup are
reported separately. A storage error can prevent the original filesystem from
reading/removing the startup journal even after native work retires. In that
case the core restores owned RAM hooks, retains the journal/update exclusion
and refuses automatic wake activation; it does not report a clean session.
The module cleanup deadline waits for healthy tracked native recording work,
while its separate EL0 execution budget and fault handling remain enforced.

`--require-h265-playback` requires actual decoder and movie-resize counters
from a compatible emulator. The checked functional backend supports the 8-bit
output path; 10-bit moving playback remains unqualified. Completed file decode
is a separate check. Explicit `--nor-profile video-settings` validates original
storage-registry rows before admitting the full native settings/backend-33
ranges. Every observed CPU erase/program and completion is checked, and the
runner compares the complete loader and MAIN before and after the sequence.
This does not emulate physical flash-busy instruction fetches or per-write
hardware readback.

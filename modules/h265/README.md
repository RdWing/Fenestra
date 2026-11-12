# H.265 bitrate app

This managed Z6III C2.01 app offers 100%, 60%, 45%, 30%, and 20% in the
Fenestra Applications menu and a Video bitrate (H.265) selector in the native
Video recording menu. It opens `camera.video.h265/v1` on a matching
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
`--video-properties` fixture. The recording control uses native H.265 10-bit
and Microphone off selections, checks fresh live view before REC, waits eight
seconds, requests Stop and requires native retirement before playback. Audit
the stopped card and complete movie decode separately. A compatible emulator
may require the explicit `--dma-copy-zero-model` diagnostic to admit mode-zero
row copies during drain; the runner records that model choice. The functional codec
and pixels are substitutes; short silent clips cannot qualify sustained rate,
GOP behavior, sound or physical-camera operation. Other native quality icons
remain separate from recorded playback metadata.

The recorded-class hook reads the published effective tier. The idle gate
refuses selection during the checked recording and drain states; a complete
per-recording snapshot and all late-writer lifetimes remain unqualified.

The current core defers context construction until the original startup
completion handler returns. Existing native workers are joined only after
publication: their task identity and exact dispatcher-event wait are checked
under the recording fence, or their callbacks acknowledge the new context.
Unknown, active or mismatched states keep the choice pending or return BUSY;
they do not trigger a persistence request merely to force readiness. This
late join has local instruction/model controls, not physical-camera timing
or complete asynchronous writer-lifetime qualification.

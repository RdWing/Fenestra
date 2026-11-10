# H.265 bitrate app

This managed Z6III C2.01 app offers 100%, 60%, 45%, 30%, and 20% in the
Fenestra Applications menu. It opens `camera.video.h265/v1` on a matching
experimental video core. Build the module with the Z63 SDK and an ID of
`h265`:

```sh
python host/build_sdk_module.py modules/h265/module.c --id h265 --target z63-c201 --required 0x390000 --native-stack-bytes 65536 --user-stack-bytes 65536 --output-dir build/h265-module
```

The choice applies to the current session. The service accepts reduced tiers
with H.265 8-bit or 10-bit selected. The existing video admission fence waits
for idle before publishing a tier or restoring 100% on stop. The ProRes and
R3D NE choices retain their own state.

The core calls the original row-copy routine and scales only the nominal rate
in an eligible H.265 row. The original selector, geometry, frame rate and GOP
fields stay in use. The linked check covers 42 eligible rows and 19 stock rows,
including AVC and retained 8K entries. Each of the five tiers is checked against
the original selector. The displayed percentages are target rates rather than
measured file bitrates.

Use `host/verify_z63_h265.py` with a pinned original EG and the linked core.
The harness runs the original selector with synthetic mode inputs and explicitly
substitutes the copy leaf, context, mutex and setting read. The full-system
`--video-test --h265-test` control checks the managed app and retirement with one
module on the card. The standalone patch's persistent settings, native Video
menu and indicators are separate feature work.

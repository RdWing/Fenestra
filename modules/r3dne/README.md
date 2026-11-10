# Z6III C2.01 R3D NE module

The R3D NE module selects RED-compatible recording metadata and the exact ZR matrix from blue-compressor commit `6ee37b7bb95074592c8989a96eaafc7ab4c23a51`. The native backend keeps the N-RAW encoder, compressed samples, capture gain and camera identity. It changes the sample entry to `NR3D`, writes the ZR matrix through the per-frame callback, and selects the `R3D` extension.

This is an offline-tested candidate. Full camera recording and deployment remain unqualified. The core remains `DO_NOT_FLASH` and has no updater envelope. Non-RAW Log3G10/RWG and CineEI are outside this package.

## Prepare the package

Use the pinned original C2.01 EG member, Python with Unicorn, and LLVM:

```sh
python3 host/prepare_z63_r3dne.py \
  --application /path/to/eg2010_0201i0.bi \
  --llvm-bin /path/to/llvm/bin \
  --linker /path/to/ld.lld \
  --output /path/to/new/r3dne-package
```

The builder produces `r3dne.wlm`, `card-layout/FENESTRA/r3dne.wlm`, the matching core candidate, an exported SDK and test results. It includes a complete source snapshot and builds from that snapshot. It compares source and SDK builds byte for byte. `PACKAGE.json` pins the matrix, module, core and test inputs. `INVENTORY.json` pins every generated file. It refuses an existing output directory.

The package uses managed WLM v3 with 65,536-byte native and user stacks. Its required capability mask is **`0x390000`**: Query, Native, Menu and Binding. Earlier R3D packages used `0x310000`, which omitted Native and could not open `camera.video.raw`. The corrected fixture uses the declared grant and checks that the old mask fails before native access.

The current loader scans `A:\FENESTRA\*.wlm` directly. It does not read a `MODULES` manifest. The card layout contains one module file and creates no startup flags or configuration. Preserve existing ProRes files and startup journals when a later authorized deployment merges this layout. The module's firmware identity alone does not identify the installed core. Use the core identity in `PACKAGE.json`.

A direct module build uses the same contract:

```sh
python3 host/build_sdk_module.py modules/r3dne/module.c \
  --target z63-c201 --id r3dne --required 0x390000 \
  --native-stack-bytes 65536 --user-stack-bytes 65536 \
  --output-dir /path/to/new/module-build
```

## Controls and capture behavior

The selection starts at Stock after each boot. In the existing Fenestra module page, the Format control offers Stock and R3D NE. Select the camera's N-RAW format first. Use N-Log for the current qualification setup. The module preserves the camera's monitoring and proxy tone. It does not force N-Log or change exposure.

A selection waits for native idle. RAW and ProRes quality share the admission mutex and counters. A conflicting ProRes request returns BUSY. Stop retains the owner until Stock restoration completes. An active fault shows `R3D NE retained. Restart` if restoration cannot complete. The status keeps wrong-mode refusal and pending idle separate.

Return to Stock before changing the camera's recording format or mode. A native format change does not retire the R3D selection. Complete isolation during mode transitions remains unqualified.

The matrix profile contains a leading zero byte and nine big-endian floats. Its 37-byte SHA-256 is `69ea56695435e553b8d3eebae0cc2b488306564f536f2c04ca73585e51431193`. The source interprets it as camera-to-XYZ D65. Its color accuracy on Z6III remains unqualified. The module adds no +0.5 EV correction or exposure sidecar. CineEI remains unavailable.

The native build generates its matrix bytes from `profile.json`. The offline converter reads the same record. Build checks pin the bytes and compare the independent numerical reference. The linked callback check compares the emitted bytes with that independent reference. The `licenses` directory retains blue-compressor's Apache-2.0 license and NOTICE. Only its matrix constants enter this implementation.

## Offline checks

The expanded linked-core check covers exact guarded matrix writes, both complete 86-byte N-RAW descriptions, unrelated copies and all thirteen filename-switch cases. It also checks Stock restoration, pending idle, active drain, conflicts, stale handles, mutex refusal and retained ownership after faults. The managed fixture checks real SDK routing with the exact package grant. These checks use synthetic native inputs and do not boot the complete firmware.

The reference converter preserves all 141 compressed RAW frames and 225,824 audio samples from the pinned C2.00 N-RAW clip. Every frame receives the exact ZR matrix. All other frame metadata and Nikon clip metadata remain unchanged. Camera identity remains NIKON Z6_3, firmware 02.00.

REDline 65.2.1 with R3DSDK 9.2.1 decodes a frame. Its EXR export uses linear output despite the requested gamma option. Resolve Studio 21.1.2.10 imports the reference as R3D NE and shows IPP2, REDWideGamutRGB, Log3G10, ISO 800 and exposure adjustment zero. It renders all 141 frames. These results establish decoder compatibility for this clip, not color accuracy or ZR capture parity.

Run the independent file checks from the source root:

```sh
python3 host/rewrap_r3d_reference.py source.NEV new.R3D
python3 host/raw_reference.py source.NEV new.R3D
python3 host/verify_z63_color_raw.py MAIN.raw
python3 host/check_z63_raw_candidate.py /path/to/core
```

The converter refuses an existing destination. `--matrix stock` gives the matrix control. `--rewrite-gamma-tags` enables a separate tag experiment. The native profile leaves Nikon gamma labels stock. Tests cover malformed descriptions, missing tags, truncated layouts and fragmented movies. Injected full-storage, short-write and finalization failures leave no partial output. Camera card-full behavior remains unqualified.

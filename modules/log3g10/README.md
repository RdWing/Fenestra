# Log3G10/RWG module boundary

The selected recording profile now derives its M1 base from the ZR R3D NE
metadata matrix: `[825,238,-22; -28,1106,-36; 5,26,1011]` in Q10. The original
producer keeps its per-body calibration multiply. `host/z63_log_profile.py`
independently derives the base and the five producer tables; it does not use
the earlier scene-fitted transform or cancel the body calibration. Its
1042/1024 scale and 24693 curve ceiling follow the standalone C2.01 patch.
The ceiling remains an explicit highlight plateau.

`host/check_z63_log_producers.py` builds the resident ARM source accessor and
runs original C2.01 jobs with supplied producer-pointer substitutions. It
checks H.265/ProRes job inputs, two body matrices, exact RGB/NLG output and
Stock restoration. These are isolated ordinary-route jobs; the accessor is
not yet installed in the live core and the color service remains gated.

View assist has separate Z6III panel profiles in
`host/z63_log_view_profile.py`: RWG to BT.709 for the rear monitor, and that
conversion composed with the original C2.01 normal-view correction for the
EVF. Coefficients must fit signed 12-bit storage. The original firmware
record is checked before generating the profiles. Do not substitute the
ZR/P3 monitor matrix or use the same matrix on both panels. Panel-specific
tone curves, cache refresh, playback/live-view transitions and physical
appearance still need validation. These monitoring profiles do not change
the recording tables.


The managed module builds for C2.01 and discovers the color service. The service reports explicit unavailable reasons and refuses nonstock activation. The C2.01 M1 matrix now has an original-code producer and movie-source binding. Its complete RGB basis and hardware order remain unresolved.

The offline verifier reproduces 687 recovered ZR curve samples. It checks the exact ZR matrix bytes from blue-compressor commit 6ee37b7bb95074592c8989a96eaafc7ab4c23a51. The matrix source is crates/core/src/r3d.rs. No external converter implementation is copied. The independently authored minimal reference uses standard BMFF and NRMT parsing with the attributed matrix constant.

Run `python3 host/log3g10_reference.py` for numerical checks. The coverage file records the missing processed-color joins. The separate R3D NE module implements RAW compatibility only. H.265, ProRes, monitoring, proxies and EI still need their own bindings and acceptance.

Run `python3 host/check_z63_m1.py /path/to/C2.01/MAIN.raw --output m1-results.json` with Unicorn installed for original ARM checks. The checker pins the firmware hash. It checks coefficient composition, all halfword encodings, the complete serializer, source selection and retained pointers. It does not emulate hardware pixels.

The direct ZR transplant is in `src/platform/z63_c201/color_transplant.c`. It builds a private candidate from supplied C2.01 parameter and sample blocks. It replaces M2, two tone controls and six Log3G10 curves. It preserves M1 calibration and the separate Nlg table. The function checks all inputs before it writes the output. The primitive retains private buffers. The separate `color_job.c` adapter copies a validated result into native job storage in offline tests. No live hook is installed.

Run the source-pinned comparison with the original firmware files and supplied ZR calibration block:

```sh
python3 host/check_zr_color_transplant.py \
  --z63 /path/to/Z6III/C2.01/MAIN.raw \
  --zr /path/to/ZR/C1.11/MAIN.raw \
  --zr-calibration /path/to/ZR-calibration.bin \
  --clang /path/to/clang --linker /path/to/ld.lld \
  --output /path/to/new/results
```

The check compares all 65,536 M2 scalar inputs with original ZR instructions. It also checks 770 matched M1 cases, eight calibration getter cases, three complete serializers, and 21 executions of the compiled ARM candidate. Original curve checks cover three ratios and all six banks. C2.01 constructors and register writers consume the candidate in synthetic memory. This is parameter and writer compatibility, not accepted H.265 or ProRes RWG recording.

The desktop pixel reference supplies a separate ordering hypothesis. Run `python3 host/check_desktop_m1_order.py --sdk /path/to/sdk-debug.arm64 --output /path/to/desktop-order.json` with Unicorn installed. It checks 4,096 M1 cases and 4,096 paired-curve cases against original SDK instruction ranges. The host supplies stack inputs and absolute values between two ranges. No instruction or called array helper is replaced. These tests confirm the desktop M1-before-curves order, signed rounding and clipping. They do not establish the camera's input color basis or hardware order.

The bounded native-job adapter now passes original C2.01 serializer, generator and static-builder tests. It writes the complete candidate into native job storage before publication. It checks the corrected packed-sample offset, source pointers, chroma scalar and ordinary H.265/ProRes guards. It has no installed live hook. Indirect consumers, shared scratch, the recording fence and the hardware color basis remain open.

Run `host/check_z63_color_job.py --help` for the native-job test. Run `host/inspect_recording_color.py clip.MOV --tools` for separate container, codec and Nikon declarations. Run `host/check_z63_color_metadata.py MAIN.raw` for original selectors and setter-failure checks.

The `mode-requests.json` file lists 95 target-format menu requests. Of these, 63 have initializer state zero for their matching file type. Neither count proves encoder admission. Each row retains unknown effective settings, image-area, quality, proxy and processing fields. Run `python3 host/check_z63_mode_requests.py MAIN.raw` to reproduce all 127 source records and 35 state overrides.

The size/rate list provider selects 63 target wire values by file type. The native setter and validator pass 92 accepted-value cases, twelve refusals and 330 validator cases. The tests supply setting reads and capture writes. A listed tuple does not establish effective recording admission. The setter also permits a mixed-format request under synthetic changing reads and ignores the batch service failure.

The separate `host/rwg_pipeline.py` implements the reconstruction method from
[NikonFirmwarePatch's Z8 colour report](https://github.com/XinmiaoZhao/NikonFirmwarePatch/blob/a21fc8c04b6dd863439c4192d387b755633287f6/docs/log-colour-report.en.md).
It inverts a supplied recording configuration, fits a linear basis from matched
samples, composes that basis with camera-to-XYZ and RWG, backs out the body's
calibration, and generates all six RGB curves, NLG, M2 and constant CPXS
compensation. It requires the basis, node scale and storage ceiling explicitly.
It rejects unconstrained RGB fits, singular matrices and non-identifiable
clipped curve inputs. The caller must supply matching linear RAW references
with the decoder's nonlinear saturation mapping removed.

Install `host/requirements-color.txt` in an analysis environment and run
`python3 -m unittest tests.test_rwg_pipeline -v`. The independent reconstruction
also reproduces 144 pinned public Z8 input samples and complete Log3G10 model
outputs. Those Z8 coefficients are reference test inputs, not a Z6III profile.
The recovered ZR curve arithmetic and its existing tests remain separate.

This code is an offline Fenestra development tool. It does not enable the color
service. A measured Z6III input basis, active processing configuration, native
publication/retirement contract and codec interpretation are still required.
Five verified C2.01 brackets now supply twenty main recordings and ten proxies,
including N-RAW before and after H.265 and ProRes N-Log. Pixel-first inversion
at frames 10, 15 and 20 improves the training fit, but the independent scene
still has roughly 6% normalized residuals in its brighter bracket. The fitted
coordinates are conditional post-stock-M1 values, not a qualified input basis.
`host/decoder_inverse.py` supplies a bounded offline inverse of the published
decoder model; small matrix perturbations support it while larger controls
remain unresolved. Neither codec has an installed calibration profile.

`fx_z63_color_rwg_candidate` in `color_transplant.c` builds the complete private
configuration: M1, M2, six RGB banks, rounded NLG and both CPXS sets. It preserves
stock N-Log routing controls and leaves all inputs unchanged. It rejects
overlapping storage, invalid controls, out-of-range M1 coefficients and curve
values above 32763, since 32764 rounds to NLG 4096 and wraps in the native
12-bit writer. This is separate from the older direct ZR tone transplant and
is not connected to `color_job.c` or a live hook.

Run the pinned C2.01 original-writer check:

```sh
python3 host/check_z63_rwg_candidate.py --main /path/to/MAIN.raw \
  --clang /path/to/clang --linker /path/to/ld.lld --output /path/to/new/results
```

Nine ARM/host cases cover 9,063
register words. The selected color, RAW-reference and recording-metadata
suites pass 40 host tests. These checks establish numerical and buffer-writing
behavior; they do not establish recording activation or hardware pixel color.
The reference Z8 ceiling of 24693 remains an explicit highlight plateau, not
a target-camera calibration choice.

The frontend consumes newer queued choices after BUSY and keeps the current
choice until the service accepts or refuses it. Refusal returns to status
readback without terminating the module. Host tests cover cancellation, retry,
retained faults and the Stock-only service gate. Those tests use a supplied
backend; they do not enable the live color path. Build a v4 frontend envelope
with `host/build_sdk_module.py --bundle` and the matching bundle-aware core.

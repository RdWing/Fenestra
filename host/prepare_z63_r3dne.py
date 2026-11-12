"""Prepare the C2.01 R3D NE module, matching core and offline checks.

The output is a local research candidate. This tool neither contacts a camera
nor creates an updater envelope. Existing output directories are refused.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tempfile

from build_z63_adapter import load_application
from module_header import validate_package
from r3dne_profile import load as load_raw_profile, MATRIX_SHA256, BLUE_COMMIT

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = 0x390000  # QUERY, NATIVE, MENU and BINDING.
STACK_BYTES = 65536


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log, environment, cwd=ROOT):
    with log.open('w', encoding='utf-8') as stream:
        subprocess.run(command, cwd=cwd, env=environment, stdout=stream,
                       stderr=subprocess.STDOUT, check=True)


def prepare(application, output, llvm_bin, linker):
    application = Path(application).resolve(strict=True)
    output = Path(output).resolve()
    llvm_bin, linker = Path(llvm_bin).resolve(strict=True), Path(linker).resolve(strict=True)
    if output.exists():
        raise ValueError('output must be a new directory')
    if not output.parent.is_dir():
        raise ValueError('output parent directory must exist')
    profile, _ = load_application(application)
    raw_profile, matrix = load_raw_profile()
    reference = json.loads((ROOT/'host/log3g10_reference.json').read_text())
    if (reference['source_commit'] != BLUE_COMMIT or len(matrix) != 37 or matrix[0] != 0
            or hashlib.sha256(matrix).hexdigest() != MATRIX_SHA256
            or matrix != bytes.fromhex(reference['matrix_hex'])
            or list(struct.unpack('>9f', matrix[1:])) != reference['matrix_xyz_d65']):
        raise ValueError('ZR matrix profile differs')
    for name, expected in raw_profile['external_source']['license_files'].items():
        if digest(ROOT/'modules/r3dne'/name) != expected:
            raise ValueError('matrix source license differs')
    environment = dict(os.environ)
    environment['PATH'] = os.pathsep.join([str(llvm_bin), str(linker.parent), environment.get('PATH', '')])
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    environment.pop('PYTHONOPTIMIZE', None)
    build_root = ROOT/'build'
    build_root.mkdir(exist_ok=True)
    # The core builder records generated paths relative to its source tree.
    # Keep staging there until all builds and checks finish, then publish once.
    with tempfile.TemporaryDirectory(prefix='r3dne-prepare-', dir=build_root) as temporary:
        stage = Path(temporary)/'bundle'
        stage.mkdir()
        checks = stage/'checks'
        checks.mkdir()
        run([sys.executable, str(ROOT/'verify_source.py')], checks/'source-inputs.log', environment)
        snapshot = stage/'source'
        inventory = json.loads((ROOT/'SOURCE-INVENTORY.json').read_text())
        for name in [row['path'] for row in inventory['files']] + ['SOURCE-INVENTORY.json']:
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                raise ValueError('unsafe source inventory path')
            destination = snapshot/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, destination)
        run([sys.executable, str(snapshot/'verify_source.py'), '--distribution'],
            checks/'source-snapshot.log', environment)
        core_output = snapshot/'build/r3dne-core'
        core_script = ('import sys; from pathlib import Path; '
                       'sys.path.insert(0,sys.argv[1]); from build_z63_probe import build; '
                       'build(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5],'
                       'menu=True,sdk=True,runtime=True,ui=True,video=True)')
        run([sys.executable, '-c', core_script, str(snapshot/'host'), str(application),
             str(core_output), str(linker), str(llvm_bin)], checks/'core-build.log', environment, snapshot)
        shutil.move(str(core_output), str(stage/'core'))
        (snapshot/'build').rmdir()
        core = json.loads((stage/'core/probe.json').read_text())
        run([sys.executable, str(snapshot/'host/export_sdk.py'), '--output', str(stage/'sdk')],
            checks/'sdk-export.log', environment, snapshot)
        source = snapshot/'modules/r3dne/module.c'
        options = [str(source), '--target', 'z63-c201', '--id', 'r3dne', '--bundle',
                   '--required', hex(CAPABILITIES), '--native-stack-bytes', str(STACK_BYTES),
                   '--user-stack-bytes', str(STACK_BYTES)]
        for name, builder in [('source', snapshot/'host/build_sdk_module.py'),
                              ('sdk', stage/'sdk/build_module.py')]:
            run([sys.executable, str(builder), *options, '--output-dir', str(stage/f'build-{name}')],
                checks/f'build-{name}.log', environment)
        module = (stage/'build-source/r3dne.wlm').read_bytes()
        if module != (stage/'build-sdk/r3dne.wlm').read_bytes():
            raise ValueError('source and SDK module builds differ')
        contract = validate_package(module, bytes.fromhex(profile['payload_sha256']), capabilities=CAPABILITIES)
        if (struct.unpack_from('<I', module, 8)[0] != 4 or contract['entry_abi'] != 1
                or contract['required'] != CAPABILITIES
                or contract['native_stack_bytes'] != STACK_BYTES or contract['user_stack_bytes'] != STACK_BYTES):
            raise ValueError('managed RAW module contract differs')
        # Direct native access is necessary to open camera.video.raw. Do not
        # confuse a valid binary header with permission to bind that service.
        try:
            validate_package(module, bytes.fromhex(profile['payload_sha256']), capabilities=0x310000)
        except ValueError:
            pass
        else:
            raise ValueError('module unexpectedly admits a grant without NATIVE')
        run([sys.executable, str(snapshot/'host/check_z63_raw_candidate.py'), str(stage/'core')],
            checks/'native-raw.json', environment, snapshot)
        run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_video_quality.py', '-v'],
            checks/'managed-lifecycle.log', environment, snapshot)
        run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_raw_reference.py', '-v'],
            checks/'offline-file-tests.log', environment, snapshot)
        run([sys.executable, str(snapshot/'verify_source.py'), '--distribution'],
            checks/'source-snapshot-final.log', environment, snapshot)
        card = stage/'card-layout/FENESTRA'
        card.mkdir(parents=True)
        (card/'r3dne.wlm').write_bytes(module)
        (stage/'r3dne.wlm').write_bytes(module)
        shutil.copyfile(snapshot/'modules/r3dne/README.md', stage/'MODULE-GUIDE.md')
        shutil.copyfile(snapshot/'modules/r3dne/profile.json', stage/'MATRIX-PROFILE.json')
        shutil.copytree(snapshot/'modules/r3dne/licenses', stage/'licenses')
        data = dict(schema='fenestra.z63-r3dne/v1', target='Z6III C2.01',
                    application_sha256=profile['application_sha256'],
                    core_candidate_sha256=core['candidate_sha256'],
                    module_sha256=hashlib.sha256(module).hexdigest(), module_contract=contract,
                    module_version=4, frontend_version=3, native_component_count=0, source_sdk_identical=True,
                    matrix=dict(profile_id=1, source_commit=BLUE_COMMIT,
                                source_path=reference['source_path'], nrmt_key='0x01900012',
                                bytes_hex=matrix.hex(), sha256=MATRIX_SHA256,
                                leading_byte=0, coefficients_be_f32=reference['matrix_xyz_d65'],
                                interpretation='camera-to-XYZ D65, from the source interpretation',
                                external_source=raw_profile['external_source'],
                                z6iii_color_accuracy_qualified=False),
                    behavior=dict(boot_selection='Stock', encoder='Stock N-RAW', capture_gain='Stock',
                                  monitoring_and_proxies='Stock camera tone', ei_available=False,
                                  exposure_offset_ev=0, exposure_sidecar=False,
                                  raw_samples_changed=False, camera_identity_changed=False),
                    offline_reference=raw_profile['offline_reference'],
                    offline_reference_scope='Preserved C2.00 decoder evidence. Preparation does not decode that clip.',
                    mode_transition_freshness_qualified=False,
                    checks=dict(native_raw=True, managed_lifecycle=True, offline_file_tests=True,
                                missing_native_capability_rejected=True),
                    discovery='A:\\FENESTRA\\*.wlm; no MODULES manifest',
                    startup_files_created=False, firmware_package=False, do_not_flash=True,
                    firmware_boot_tested=False, physical_tests=0,
                    source_inventory_sha256=digest(snapshot/'SOURCE-INVENTORY.json'),
                    source_hashes={name:digest(snapshot/name) for name in [
                        'host/prepare_z63_r3dne.py', 'modules/r3dne/module.c',
                        'host/r3dne_profile.py', 'modules/r3dne/profile.json',
                        'host/check_z63_raw_candidate.py', 'host/log3g10_reference.json',
                        'tests/raw_module_fixture.c', 'tests/test_video_quality.py',
                        'host/raw_reference.py', 'host/rewrap_r3d_reference.py', 'tests/test_raw_reference.py']})
        (stage/'PACKAGE.json').write_text(json.dumps(data, indent=2)+'\n')
        rows = [dict(path=p.relative_to(stage).as_posix(), bytes=p.stat().st_size, sha256=digest(p))
                for p in sorted(stage.rglob('*')) if p.is_file()]
        (stage/'INVENTORY.json').write_text(json.dumps(dict(schema=1, files=rows), indent=2)+'\n')
        # Copy under the destination parent before rename. Cross-device or
        # full-storage failure then leaves no partially published output.
        with tempfile.TemporaryDirectory(prefix='.r3dne-publish-', dir=output.parent) as publishing:
            destination = Path(publishing)/'bundle'
            shutil.copytree(stage, destination)
            if output.exists():
                raise ValueError('output appeared during preparation')
            destination.rename(output)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True, help='original C2.01 EG member')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--llvm-bin', type=Path, required=True)
    parser.add_argument('--linker', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.application, args.output, args.llvm_bin, args.linker)
    print(json.dumps({k:result[k] for k in ['target', 'module_sha256', 'core_candidate_sha256',
                                          'module_version', 'checks', 'do_not_flash']}, indent=2))


if __name__ == '__main__':
    main()

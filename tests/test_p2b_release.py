import json
import os
import tempfile
import unittest
from pathlib import Path

import mv_core
from mv_version import ARTIFACT_VERSION,VERSION,WINDOWS_VERSION,read_version,windows_numeric_version
from release_tool import (
    BOOTSTRAP_LOCK_PACKAGES,
    MAIN_LOCK_PACKAGES,
    binary_record,
    create_sbom,
    load_binary_metadata,
    parse_lock,
    release_metadata,
    sha256_file,
    validate_manifest,
    validate_sbom,
    verify_package,
    version_payload,
    write_json,
)


ROOT=Path(__file__).resolve().parents[1]


class P2BReleaseEngineeringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def executable(self,name,identity):
        path=self.base/name
        path.write_text(f'#!/bin/sh\nprintf "%s\\n" "{identity}"\n',encoding='utf8')
        path.chmod(0o755)
        return path

    def binary_metadata(self,with_ffmpeg=True):
        probe=self.executable('ffprobe.exe','ffprobe version synthetic-7.1')
        records=[binary_record(probe,'ffprobe',True,'synthetic test fixture')]
        if with_ffmpeg:
            encoder=self.executable('ffmpeg.exe','ffmpeg version synthetic-7.1')
            records.append(binary_record(encoder,'ffmpeg',False,'synthetic test fixture'))
        else:
            records.append({'name':'ffmpeg','required':False,'present':False,'origin':'not bundled'})
        path=self.base/'external-binaries.json'
        write_json(path,{'format':'MovieVault External Binary Provenance 1','binaries':records})
        return path

    def package(self,with_ffmpeg=False):
        package=Path(tempfile.mkdtemp(prefix='package-',dir=self.base))
        for relative in ('web/index.html','web/app.js','web/style.css','vendor/ffprobe.exe','webview/support.dat','pythonnet/runtime/Python.Runtime.dll'):
            path=package/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic fixture')
        (package/'MovieVault.exe').write_bytes(b'synthetic executable')
        (package/'VERSION').write_text(VERSION+'\n',encoding='ascii')
        metadata=self.binary_metadata(with_ffmpeg)
        records=load_binary_metadata(metadata)
        probe=next(item for item in records if item['name']=='ffprobe')
        (package/'vendor/ffprobe.exe').write_bytes((self.base/'ffprobe.exe').read_bytes())
        self.assertEqual(probe['sha256'],sha256_file(package/'vendor/ffprobe.exe'))
        if with_ffmpeg:
            (package/'vendor/ffmpeg.exe').write_bytes((self.base/'ffmpeg.exe').read_bytes())
            (package/'vendor/ffmpeg.exe').chmod(0o755)
        (package/'vendor/ffprobe.exe').chmod(0o755)
        write_json(package/'external-binaries.json',json.loads(metadata.read_text(encoding='utf8')))
        write_json(package/'release-metadata.json',release_metadata(metadata,'UNSIGNED'))
        write_json(package/'MovieVault.spdx.json',create_sbom(ROOT/'requirements-windows.lock',metadata,'UNSIGNED'))
        return package

    def test_authoritative_version_drives_runtime_and_artifact_names(self):
        self.assertEqual(read_version(ROOT/'VERSION'),VERSION)
        self.assertEqual(mv_core.VERSION,VERSION)
        self.assertEqual(WINDOWS_VERSION,windows_numeric_version(VERSION))
        payload=version_payload()
        self.assertEqual(payload['portable_name'],f'MovieVault_{ARTIFACT_VERSION}_Portable.zip')
        self.assertEqual(payload['setup_name'],f'MovieVault_Setup_{ARTIFACT_VERSION}.exe')

    def test_semantic_to_windows_version_mapping_is_deterministic(self):
        self.assertEqual(windows_numeric_version('2.0.0-rc.3'),'2.0.0.3')
        self.assertEqual(windows_numeric_version('2.1.4'),'2.1.4.0')
        with self.assertRaises(ValueError):windows_numeric_version('2.0')
        with self.assertRaises(ValueError):windows_numeric_version('2.0.0-rc.70000')

    def test_runtime_build_installer_and_visual_smoke_have_no_independent_current_version(self):
        self.assertIn('from mv_version import VERSION',(ROOT/'mv_core.py').read_text(encoding='utf8'))
        self.assertIn('from mv_version import VERSION',(ROOT/'tests/visual_smoke.py').read_text(encoding='utf8'))
        for name in ('build_windows.ps1','BUILD_WINDOWS.cmd','MovieVault.iss'):
            text=(ROOT/name).read_text(encoding='utf8')
            self.assertNotIn('2.0.0-rc.3',text,name)
            self.assertNotIn('RC1',text,name)

    def test_release_and_bootstrap_locks_are_exact_complete_and_hashed(self):
        main=parse_lock(ROOT/'requirements-windows.lock',MAIN_LOCK_PACKAGES)
        bootstrap=parse_lock(ROOT/'requirements-build.lock',BOOTSTRAP_LOCK_PACKAGES)
        self.assertEqual(len(main),16);self.assertEqual(len(bootstrap),4)
        self.assertNotIn('playwright',{row['normalized_name'] for row in main})
        self.assertTrue(all(len(row['sha256'])==64 for row in main+bootstrap))

    def test_invalid_or_incomplete_lock_is_rejected(self):
        lock=self.base/'bad.lock';lock.write_text('Pillow>=10\n',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'exact hashed'):parse_lock(lock)
        lock.write_text('Pillow==12.3.0 --hash=sha256:'+'0'*64+'\n',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'package set mismatch'):parse_lock(lock,MAIN_LOCK_PACKAGES)

    def test_build_uses_only_hashed_locks_and_mandatory_gates(self):
        text=(ROOT/'build_windows.ps1').read_text(encoding='utf8')
        self.assertGreaterEqual(text.count('--require-hashes'),2)
        self.assertNotIn('pip install -r requirements-windows.txt',text)
        for gate in ('Automated test suite','PyInstaller packaging','SPDX SBOM validation','Packaged-content verification','Release-manifest validation'):
            self.assertIn(gate,text)
        self.assertGreater(text.index('All requested build, verification, and packaging steps completed successfully.'),text.index('Inno Setup compilation'))
        self.assertIn("exit 1",text);self.assertIn("exit 0",text)

    def test_batch_wrapper_preserves_powershell_failure_and_forwards_arguments(self):
        text=(ROOT/'BUILD_WINDOWS.cmd').read_text(encoding='utf8')
        self.assertIn('build_windows.ps1" %*',text)
        self.assertIn('set "BUILD_EXIT=%ERRORLEVEL%"',text)
        self.assertIn('exit /b %BUILD_EXIT%',text)
        self.assertTrue(text.rstrip().endswith('exit /b 0'))

    def test_binary_provenance_records_executed_identity_and_hash(self):
        metadata=self.binary_metadata(True);records=load_binary_metadata(metadata)
        self.assertEqual([item['name'] for item in records],['ffprobe','ffmpeg'])
        self.assertIn('synthetic-7.1',records[0]['identity'])
        self.assertEqual(len(records[0]['sha256']),64)
        self.assertNotIn(str(self.base),metadata.read_text(encoding='utf8'))

    def test_spdx_sbom_contains_runtime_build_and_external_components(self):
        metadata=self.binary_metadata(True)
        path=self.base/'MovieVault.spdx.json';write_json(path,create_sbom(ROOT/'requirements-windows.lock',metadata,'UNSIGNED'))
        result=validate_sbom(path);self.assertGreaterEqual(result['packages'],20)
        data=json.loads(path.read_text(encoding='utf8'));names={item['name'] for item in data['packages']}
        self.assertTrue({'MovieVault','Python','pyinstaller','pywebview','Pillow','ffprobe','ffmpeg'}<=names)

    def test_package_verifier_emits_and_revalidates_complete_manifest(self):
        package=self.package(True);manifest=package/'release-manifest.json'
        result=verify_package(package,manifest,True)
        self.assertGreaterEqual(result['files'],12);self.assertEqual(result['signing_state'],'UNSIGNED')
        records=json.loads(manifest.read_text(encoding='utf8'))['files']
        self.assertTrue(all(len(record['sha256'])==64 for record in records))
        self.assertEqual(validate_manifest(package,manifest)['files'],result['files'])
        (package/'web/app.js').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'manifest mismatch'):validate_manifest(package,manifest)

    def test_package_verifier_rejects_missing_runtime_support(self):
        package=self.package(False);(package/'pythonnet/runtime/Python.Runtime.dll').unlink()
        with self.assertRaisesRegex(ValueError,'Python.Runtime.dll'):verify_package(package,package/'release-manifest.json',False)
        (package/'pythonnet/runtime/Python.Runtime.dll').write_bytes(b'fixture')
        (package/'webview/support.dat').unlink()
        with self.assertRaisesRegex(ValueError,'pywebview'):verify_package(package,package/'release-manifest.json',False)

    def test_package_verifier_rejects_missing_exe_web_assets_and_ffprobe(self):
        for relative in ('MovieVault.exe','web/index.html','web/app.js','web/style.css','vendor/ffprobe.exe'):
            with self.subTest(relative=relative):
                package=self.package(False);(package/relative).unlink()
                with self.assertRaisesRegex(ValueError,'missing mandatory files'):
                    verify_package(package,package/'release-manifest.json',False)

    def test_package_verifier_cross_checks_provenance_metadata_and_sbom(self):
        package=self.package(False)
        metadata=json.loads((package/'release-metadata.json').read_text(encoding='utf8'))
        metadata['external_binaries'][0]['sha256']='0'*64
        write_json(package/'release-metadata.json',metadata)
        with self.assertRaisesRegex(ValueError,'does not match binary provenance'):
            verify_package(package,package/'release-manifest.json',False)
        package=self.package(False)
        sbom=json.loads((package/'MovieVault.spdx.json').read_text(encoding='utf8'))
        probe=next(item for item in sbom['packages'] if item['name']=='ffprobe')
        probe['checksums'][0]['checksumValue']='0'*64
        write_json(package/'MovieVault.spdx.json',sbom)
        with self.assertRaisesRegex(ValueError,'SBOM does not match ffprobe provenance'):
            verify_package(package,package/'release-manifest.json',False)

    def test_package_verifier_rejects_credentials_databases_media_and_development_files(self):
        cases=('movievault.sqlite','.env','private.pfx','sample.mkv','requirements-qa.txt','tests/leak.txt')
        for relative in cases:
            with self.subTest(relative=relative):
                package=self.package(False);path=package/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'forbidden')
                with self.assertRaisesRegex(ValueError,'Forbidden package member'):verify_package(package,package/'release-manifest.json',False)

    def test_signing_is_real_or_explicitly_unsigned_without_embedded_secrets(self):
        text=(ROOT/'build_windows.ps1').read_text(encoding='utf8')
        for marker in ('signtool.exe','MOVIEVAULT_SIGN_CERT_THUMBPRINT','MOVIEVAULT_SIGN_CERT_PATH','MOVIEVAULT_SIGN_TIMESTAMP_URL','verify /pa /all',"$signingState = 'UNSIGNED'"):
            self.assertIn(marker,text)
        self.assertFalse(any(path.suffix.lower() in {'.pfx','.p12','.pem','.key'} for path in ROOT.rglob('*') if path.is_file()))
        metadata=self.binary_metadata(False)
        self.assertEqual(release_metadata(metadata,'UNSIGNED')['signing']['state'],'UNSIGNED')
        with self.assertRaises(ValueError):release_metadata(metadata,'pretend-signed')

    def test_installer_requires_authoritative_version_defines(self):
        installer=(ROOT/'MovieVault.iss').read_text(encoding='utf8')
        for define in ('MyAppVersion','MyWindowsVersion','MySetupBaseName'):
            self.assertIn(f'#ifndef {define}',installer)
        build=(ROOT/'build_windows.ps1').read_text(encoding='utf8')
        self.assertIn('/DMyAppVersion=',build);self.assertIn('/DMyWindowsVersion=',build);self.assertIn('/DMySetupBaseName=',build)


if __name__=='__main__':unittest.main()

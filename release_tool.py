"""Deterministic, dependency-free MovieVault release metadata and package checks."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from mv_gemini import GEMINI_CREDENTIAL_FILENAME
from mv_tmdb import TMDB_CREDENTIAL_FILENAME
from mv_version import ARTIFACT_VERSION,VERSION,WINDOWS_VERSION,read_version

MAIN_LOCK_PACKAGES={
    'altgraph','bottle','cffi','clr-loader','packaging','pefile','pillow','proxy-tools','pycparser',
    'pyinstaller','pyinstaller-hooks-contrib','pythonnet','pywebview','pywin32-ctypes','setuptools','typing-extensions',
}
BOOTSTRAP_LOCK_PACKAGES={'packaging','pip','setuptools','wheel'}
LOCK_LINE=re.compile(r'^([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:([0-9a-f]{64})$')
SHA256_RE=re.compile(r'^[0-9a-f]{64}$')
MEDIA_SUFFIXES={'.mkv','.mp4','.m4v','.avi','.mov','.wmv','.webm','.mpg','.mpeg','.ts','.m2ts','.flv','.srt','.ass','.ssa','.vtt'}


def normalized_name(value:str) -> str:return re.sub(r'[-_.]+','-',value).lower()


def sha256_file(path:Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def write_json(path:Path,payload:dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.partial')
    temporary.write_text(json.dumps(payload,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf8')
    os.replace(temporary,path)


def parse_lock(path:Path,expected:set[str]|None=None) -> list[dict]:
    records=[]
    for number,line in enumerate(path.read_text(encoding='utf8').splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('#'):continue
        match=LOCK_LINE.fullmatch(stripped)
        if not match:raise ValueError(f'{path.name}:{number} is not an exact hashed requirement')
        name,version,digest=match.groups();normalized=normalized_name(name)
        if any(record['normalized_name']==normalized for record in records):raise ValueError(f'Duplicate locked package: {name}')
        records.append({'name':name,'normalized_name':normalized,'version':version,'sha256':digest})
    names={record['normalized_name'] for record in records}
    if expected is not None and names!=expected:
        missing=sorted(expected-names);extra=sorted(names-expected)
        raise ValueError(f'Lock package set mismatch; missing={missing}, extra={extra}')
    if 'playwright' in names:raise ValueError('Playwright is QA-only and must not enter the Windows release lock')
    return records


def version_payload() -> dict:
    return {
        'product':'MovieVault','semantic_version':VERSION,'windows_numeric_version':WINDOWS_VERSION,
        'artifact_version':ARTIFACT_VERSION,
        'portable_name':f'MovieVault_{ARTIFACT_VERSION}_Portable.zip',
        'setup_name':f'MovieVault_Setup_{ARTIFACT_VERSION}.exe',
    }


def pyinstaller_version_text() -> str:
    parts=','.join(WINDOWS_VERSION.split('.'))
    return f'''# UTF-8\nVSVersionInfo(\n  ffi=FixedFileInfo(filevers=({parts}), prodvers=({parts}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n  kids=[StringFileInfo([StringTable('040904B0',[\n    StringStruct('CompanyName','MovieVault Personal Library'),\n    StringStruct('FileDescription','MovieVault local movie catalog'),\n    StringStruct('FileVersion','{VERSION}'),\n    StringStruct('InternalName','MovieVault'),\n    StringStruct('OriginalFilename','MovieVault.exe'),\n    StringStruct('ProductName','MovieVault v2'),\n    StringStruct('ProductVersion','{VERSION}')\n  ])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])\n'''


def binary_record(path:Path,name:str,required:bool,origin:str) -> dict:
    if not path.is_file():
        if required:raise ValueError(f'Required {name} binary is missing')
        return {'name':name,'required':False,'present':False,'origin':origin}
    try:
        result=subprocess.run([str(path),'-version'],capture_output=True,text=True,timeout=15,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:raise ValueError(f'{name} could not be executed for provenance') from exc
    if result.returncode!=0:raise ValueError(f'{name} -version failed with exit code {result.returncode}')
    identity=next((line.strip() for line in result.stdout.splitlines() if line.strip()),'version output unavailable')[:300]
    return {'name':name,'required':required,'present':True,'origin':origin,'identity':identity,'sha256':sha256_file(path),'size':path.stat().st_size}


def load_binary_metadata(path:Path) -> list[dict]:
    data=json.loads(path.read_text(encoding='utf8'))
    binaries=data.get('binaries')
    if not isinstance(binaries,list):raise ValueError('Binary metadata has no binaries list')
    if [item.get('name') for item in binaries]!=['ffprobe','ffmpeg']:raise ValueError('Binary metadata must describe ffprobe then ffmpeg exactly once')
    probe=next((item for item in binaries if item.get('name')=='ffprobe'),None)
    if not probe or not probe.get('present') or not SHA256_RE.fullmatch(str(probe.get('sha256',''))):
        raise ValueError('Binary metadata does not contain a valid required ffprobe record')
    for item in binaries:
        expected_keys={'name','required','present','origin'}|({'identity','sha256','size'} if item.get('present') else set())
        if set(item)!=expected_keys:raise ValueError('External binary provenance has missing or unexpected fields')
        if item.get('present') and not SHA256_RE.fullmatch(str(item.get('sha256',''))):raise ValueError('Invalid external binary SHA-256')
        if item.get('present') and (not item.get('identity') or not item.get('origin')):raise ValueError('External binary provenance is incomplete')
        if any(key in json.dumps(item).lower() for key in ('password','private key')):raise ValueError('Sensitive material in binary metadata')
    return binaries


def release_metadata(binary_metadata:Path,build_mode:str,application_signing_state:str,setup_signing_state:str|None=None) -> dict:
    if build_mode not in ('portable','full'):raise ValueError('Build mode must be portable or full')
    if application_signing_state not in ('SIGNED','UNSIGNED'):raise ValueError('Application signing state must be SIGNED or UNSIGNED')
    if build_mode=='portable' and setup_signing_state is not None:raise ValueError('Portable metadata must not declare a Setup artifact')
    if build_mode=='full' and setup_signing_state not in ('SIGNED','UNSIGNED'):raise ValueError('Full metadata requires a produced Setup signing state')
    version=version_payload()
    artifacts={'MovieVault.exe':{'type':'application','present':True,'signing_state':application_signing_state}}
    payload={
        'format':'MovieVault Release Metadata 2','product':'MovieVault',
        'semantic_version':version['semantic_version'],'windows_numeric_version':version['windows_numeric_version'],
        'artifact_version':version['artifact_version'],'portable_name':version['portable_name'],
        'build_mode':build_mode,'artifacts':artifacts,
        'build_context':{'python':platform.python_version(),'implementation':platform.python_implementation(),'architecture':platform.machine()},
        'external_binaries':load_binary_metadata(binary_metadata),
        'windows_acceptance_tested':False,
    }
    if build_mode=='full':
        payload['setup_name']=version['setup_name']
        artifacts[version['setup_name']]={'type':'installer','present':True,'signing_state':setup_signing_state}
    return validate_release_metadata(payload)


def validate_release_metadata(source:Path|dict) -> dict:
    data=json.loads(source.read_text(encoding='utf8')) if isinstance(source,Path) else source
    if not isinstance(data,dict) or data.get('format')!='MovieVault Release Metadata 2':raise ValueError('Invalid release metadata format')
    mode=data.get('build_mode')
    if mode not in ('portable','full'):raise ValueError('Release metadata has invalid build mode')
    expected_keys={'format','product','semantic_version','windows_numeric_version','artifact_version','portable_name','build_mode','artifacts','build_context','external_binaries','windows_acceptance_tested'}
    if mode=='full':expected_keys.add('setup_name')
    if set(data)!=expected_keys:raise ValueError('Release metadata contains missing or unexpected fields')
    if data.get('product')!='MovieVault' or data.get('semantic_version')!=VERSION or data.get('windows_numeric_version')!=WINDOWS_VERSION:raise ValueError('Release metadata version drift')
    if data.get('artifact_version')!=ARTIFACT_VERSION or data.get('portable_name')!=version_payload()['portable_name']:raise ValueError('Release metadata artifact-name drift')
    artifacts=data.get('artifacts')
    expected_artifacts={'MovieVault.exe'} if mode=='portable' else {'MovieVault.exe',version_payload()['setup_name']}
    if not isinstance(artifacts,dict) or set(artifacts)!=expected_artifacts:raise ValueError('Release metadata artifact set does not match build mode')
    if mode=='full' and data.get('setup_name')!=version_payload()['setup_name']:raise ValueError('Release metadata Setup name drift')
    for name,record in artifacts.items():
        expected_type='application' if name=='MovieVault.exe' else 'installer'
        if not isinstance(record,dict) or set(record)!={'type','present','signing_state'}:raise ValueError('Release artifact metadata has invalid shape')
        if record.get('type')!=expected_type or record.get('present') is not True or record.get('signing_state') not in ('SIGNED','UNSIGNED'):
            raise ValueError('Release artifact metadata has invalid state')
    context=data.get('build_context')
    if not isinstance(context,dict) or set(context)!={'python','implementation','architecture'}:raise ValueError('Release build context has invalid shape')
    if data.get('windows_acceptance_tested') is not False:raise ValueError('Release metadata must not predeclare Windows acceptance')
    if not isinstance(data.get('external_binaries'),list):raise ValueError('Release metadata external binaries have invalid shape')
    return data


def spdx_id(name:str) -> str:return 'SPDXRef-'+re.sub(r'[^A-Za-z0-9.-]+','-',name).strip('-')


def spdx_package(name:str,version:str,checksum:str|None=None,comment:str='') -> dict:
    package={
        'name':name,'SPDXID':spdx_id(name),'versionInfo':version,'downloadLocation':'NOASSERTION',
        'filesAnalyzed':False,'licenseConcluded':'NOASSERTION','licenseDeclared':'NOASSERTION','copyrightText':'NOASSERTION',
    }
    if checksum:package['checksums']=[{'algorithm':'SHA256','checksumValue':checksum}]
    if comment:package['comment']=comment
    return package


def create_sbom(lock:Path,binary_metadata:Path) -> dict:
    locked=parse_lock(lock,MAIN_LOCK_PACKAGES);binaries=load_binary_metadata(binary_metadata)
    packages=[spdx_package('MovieVault',VERSION),spdx_package('Python',platform.python_version())]
    packages.extend(spdx_package(record['name'],record['version'],record['sha256'],'Hash identifies the locked release distribution artifact.') for record in locked)
    for binary in binaries:
        if binary.get('present'):
            packages.append(spdx_package(binary['name'],binary.get('identity','unknown'),binary['sha256'],f"{binary['origin']}; {'required' if binary['required'] else 'optional'} external executable"))
    namespace_hash=hashlib.sha256((VERSION+'|'.join(sorted(package['name']+package.get('versionInfo','') for package in packages))).encode()).hexdigest()[:20]
    movie_id=spdx_id('MovieVault')
    python_id=next(package['SPDXID'] for package in packages if normalized_name(package['name'])=='python')
    pyinstaller_id=next(package['SPDXID'] for package in packages if normalized_name(package['name'])=='pyinstaller')
    relationships=[{'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':movie_id}]
    relationships.extend({'spdxElementId':movie_id,'relationshipType':'DEPENDS_ON','relatedSpdxElement':package['SPDXID']} for package in packages if package['SPDXID'] not in (movie_id,python_id,pyinstaller_id))
    relationships.append({'spdxElementId':pyinstaller_id,'relationshipType':'BUILD_DEPENDENCY_OF','relatedSpdxElement':movie_id})
    return {
        'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT',
        'name':f'MovieVault-{VERSION}-Windows-SBOM','documentNamespace':f'https://movievault.invalid/spdx/{VERSION}/{namespace_hash}',
        'creationInfo':{'created':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'creators':['Tool: MovieVault release_tool.py']},
        'packages':packages,'relationships':relationships,
    }


def validate_sbom(path:Path) -> dict:
    data=json.loads(path.read_text(encoding='utf8'))
    for key in ('spdxVersion','dataLicense','SPDXID','name','documentNamespace','creationInfo','packages','relationships'):
        if key not in data:raise ValueError(f'SBOM missing {key}')
    if data['spdxVersion']!='SPDX-2.3' or data['dataLicense']!='CC0-1.0':raise ValueError('SBOM is not SPDX 2.3 JSON')
    packages=data['packages']
    if not isinstance(packages,list):raise ValueError('SBOM packages must be a list')
    by_name={normalized_name(str(item.get('name',''))):item for item in packages}
    required={'movievault','python','pyinstaller','pywebview','pillow','ffprobe'}
    if not required<=set(by_name):raise ValueError(f'SBOM missing required components: {sorted(required-set(by_name))}')
    if by_name['movievault'].get('versionInfo')!=VERSION:raise ValueError('SBOM MovieVault version drift')
    identifiers={'SPDXRef-DOCUMENT'}|{str(item.get('SPDXID','')) for item in packages}
    for relationship in data['relationships']:
        if relationship.get('spdxElementId') not in identifiers or relationship.get('relatedSpdxElement') not in identifiers:
            raise ValueError('SBOM relationship references an unknown SPDX element')
    for binary in ('ffprobe','ffmpeg'):
        if binary in by_name:
            checks=by_name[binary].get('checksums',[])
            if not any(check.get('algorithm')=='SHA256' and SHA256_RE.fullmatch(str(check.get('checksumValue',''))) for check in checks):
                raise ValueError(f'SBOM {binary} has no SHA-256')
    serialized=json.dumps(data).lower()
    for forbidden in ('tmdb_token','gemini_api_key','private key','movievault.sqlite'):
        if forbidden in serialized:raise ValueError('SBOM contains forbidden sensitive/local material')
    return {'packages':len(packages),'version':VERSION}


def forbidden_package_path(relative:Path) -> str|None:
    lowered=[part.lower() for part in relative.parts];name=relative.name.lower()
    if any(part in {'tests','qa_reports','.git','user_data'} for part in lowered):return 'development or user-data directory'
    if name in {'.env','movievault.sqlite','tmdb_credentials.bin','gemini_credentials.bin',TMDB_CREDENTIAL_FILENAME,GEMINI_CREDENTIAL_FILENAME,'restore_pending.zip'}:return 'credential, database, or restore data'
    if relative.suffix.lower() in MEDIA_SUFFIXES:return 'movie or subtitle media'
    if relative.suffix.lower() in {'.db','.sqlite','.bak','.pfx','.p12','.pem','.key','.spec'}:return 'database, backup, private key, or build file'
    if name.startswith('requirements') or name in {'build_windows.cmd','build_windows.ps1','qa_runner.py'}:return 'development-only build input'
    if relative.suffix.lower()=='.zip':return 'nested backup/archive'
    return None


def package_files(root:Path,manifest:Path) -> list[Path]:
    files=[]
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError(f'Package contains symlink: {path.relative_to(root)}')
        if not path.is_file() or path.resolve()==manifest.resolve():continue
        relative=path.relative_to(root);reason=forbidden_package_path(relative)
        if reason:raise ValueError(f'Forbidden package member ({reason}): {relative.as_posix()}')
        files.append(path)
    return sorted(files,key=lambda item:item.relative_to(root).as_posix().lower())


def verify_package(root:Path,manifest:Path,expect_ffmpeg:bool) -> dict:
    root=root.resolve();manifest=manifest.resolve()
    if manifest.parent!=root:raise ValueError('Release manifest must be at package root')
    required=['MovieVault.exe','VERSION','web/index.html','web/app.js','web/style.css','vendor/ffprobe.exe','external-binaries.json','MovieVault.spdx.json','release-metadata.json']
    missing=[name for name in required if not (root/name).is_file()]
    if missing:raise ValueError(f'Package missing mandatory files: {missing}')
    if read_version(root/'VERSION')!=VERSION:raise ValueError('Packaged VERSION does not match the release authority')
    actual_ffmpeg=(root/'vendor/ffmpeg.exe').is_file()
    if actual_ffmpeg!=expect_ffmpeg:raise ValueError('Packaged ffmpeg presence does not match release metadata')
    files=package_files(root,manifest);relatives=[path.relative_to(root) for path in files]
    if not any(path.name.lower()=='python.runtime.dll' for path in relatives):raise ValueError('Package missing Python.Runtime.dll support file')
    if not any(any(part.lower()=='webview' for part in path.parts) for path in relatives):raise ValueError('Package missing pywebview support files')
    validate_sbom(root/'MovieVault.spdx.json')
    sbom=json.loads((root/'MovieVault.spdx.json').read_text(encoding='utf8'))
    sbom_packages={normalized_name(item['name']):item for item in sbom['packages']}
    binary_metadata=load_binary_metadata(root/'external-binaries.json')
    packaged_probe=next(item for item in binary_metadata if item.get('name')=='ffprobe')
    if packaged_probe['sha256']!=sha256_file(root/'vendor/ffprobe.exe'):
        raise ValueError('Packaged ffprobe does not match its provenance record')
    packaged_encoder=next((item for item in binary_metadata if item.get('name')=='ffmpeg'),None)
    if actual_ffmpeg and (not packaged_encoder or packaged_encoder.get('sha256')!=sha256_file(root/'vendor/ffmpeg.exe')):
        raise ValueError('Packaged ffmpeg does not match its provenance record')
    metadata=validate_release_metadata(root/'release-metadata.json')
    if metadata.get('external_binaries')!=binary_metadata:raise ValueError('Release metadata does not match binary provenance')
    for binary in binary_metadata:
        if not binary.get('present'):continue
        checks=sbom_packages.get(binary['name'],{}).get('checksums',[])
        if not any(check.get('algorithm')=='SHA256' and check.get('checksumValue')==binary['sha256'] for check in checks):
            raise ValueError(f'SBOM does not match {binary["name"]} provenance')
    entries=[{'path':path.relative_to(root).as_posix(),'size':path.stat().st_size,'sha256':sha256_file(path)} for path in files]
    payload={'format':'MovieVault Release Manifest 1','product':'MovieVault','version':VERSION,'windows_numeric_version':WINDOWS_VERSION,'build_mode':metadata['build_mode'],'artifacts':metadata['artifacts'],'ffmpeg_bundled':actual_ffmpeg,'files':entries}
    write_json(manifest,payload)
    return {'files':len(entries),'ffmpeg_bundled':actual_ffmpeg,'build_mode':payload['build_mode'],'artifacts':payload['artifacts']}


def validate_manifest(root:Path,manifest:Path) -> dict:
    data=json.loads(manifest.read_text(encoding='utf8'))
    if data.get('format')!='MovieVault Release Manifest 1' or data.get('version')!=VERSION:raise ValueError('Invalid release manifest metadata')
    metadata=validate_release_metadata(root/'release-metadata.json')
    if data.get('build_mode')!=metadata['build_mode'] or data.get('artifacts')!=metadata['artifacts']:raise ValueError('Release manifest artifact metadata mismatch')
    expected={path.relative_to(root).as_posix():path for path in package_files(root,manifest)}
    records=data.get('files')
    if not isinstance(records,list) or {record.get('path') for record in records}!=set(expected):raise ValueError('Release manifest file set mismatch')
    for record in records:
        path=expected[record['path']]
        if record.get('size')!=path.stat().st_size or record.get('sha256')!=sha256_file(path):raise ValueError(f'Release manifest mismatch: {record["path"]}')
        if not SHA256_RE.fullmatch(str(record.get('sha256',''))):raise ValueError('Release manifest contains invalid SHA-256')
    return {'files':len(records),'version':VERSION}


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('version')
    command=sub.add_parser('pyinstaller-version');command.add_argument('--output',type=Path,required=True)
    command=sub.add_parser('validate-lock');command.add_argument('--lock',type=Path,required=True);command.add_argument('--bootstrap',action='store_true')
    command=sub.add_parser('binary-metadata');command.add_argument('--output',type=Path,required=True);command.add_argument('--ffprobe',type=Path,required=True);command.add_argument('--ffprobe-origin',required=True);command.add_argument('--ffmpeg',type=Path);command.add_argument('--ffmpeg-origin',default='not bundled')
    command=sub.add_parser('release-metadata');command.add_argument('--output',type=Path,required=True);command.add_argument('--binary-metadata',type=Path,required=True);command.add_argument('--build-mode',choices=('portable','full'),required=True);command.add_argument('--application-signing-state',choices=('SIGNED','UNSIGNED'),required=True);command.add_argument('--setup-signing-state',choices=('SIGNED','UNSIGNED'))
    command=sub.add_parser('sbom');command.add_argument('--output',type=Path,required=True);command.add_argument('--lock',type=Path,required=True);command.add_argument('--binary-metadata',type=Path,required=True)
    command=sub.add_parser('validate-sbom');command.add_argument('path',type=Path)
    command=sub.add_parser('verify-package');command.add_argument('--root',type=Path,required=True);command.add_argument('--manifest',type=Path,required=True);command.add_argument('--expect-ffmpeg',choices=('present','absent'),required=True)
    command=sub.add_parser('validate-manifest');command.add_argument('--root',type=Path,required=True);command.add_argument('--manifest',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.command=='version':result=version_payload()
    elif args.command=='pyinstaller-version':args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(pyinstaller_version_text(),encoding='utf8');result={'output':args.output.name,**version_payload()}
    elif args.command=='validate-lock':result={'packages':len(parse_lock(args.lock,BOOTSTRAP_LOCK_PACKAGES if args.bootstrap else MAIN_LOCK_PACKAGES)),'lock':args.lock.name}
    elif args.command=='binary-metadata':
        binaries=[binary_record(args.ffprobe,'ffprobe',True,args.ffprobe_origin)]
        binaries.append(binary_record(args.ffmpeg,'ffmpeg',False,args.ffmpeg_origin) if args.ffmpeg else {'name':'ffmpeg','required':False,'present':False,'origin':'not bundled'})
        write_json(args.output,{'format':'MovieVault External Binary Provenance 1','binaries':binaries});result={'output':args.output.name,'binaries':binaries}
    elif args.command=='release-metadata':
        metadata=release_metadata(args.binary_metadata,args.build_mode,args.application_signing_state,args.setup_signing_state)
        write_json(args.output,metadata);result={'output':args.output.name,'build_mode':metadata['build_mode'],'artifacts':metadata['artifacts']}
    elif args.command=='sbom':write_json(args.output,create_sbom(args.lock,args.binary_metadata));result=validate_sbom(args.output)
    elif args.command=='validate-sbom':result=validate_sbom(args.path)
    elif args.command=='verify-package':result=verify_package(args.root,args.manifest,args.expect_ffmpeg=='present')
    elif args.command=='validate-manifest':result=validate_manifest(args.root,args.manifest)
    else:raise AssertionError(args.command)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        print(f'Release validation failed: {exc}',file=sys.stderr);raise SystemExit(2)

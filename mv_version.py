"""MovieVault release version loaded from the one authoritative VERSION file."""
from __future__ import annotations

import re
import sys
from pathlib import Path

SEMVER_PATTERN=re.compile(
    r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)'
    r'(?P<prerelease>-rc\.(?P<rc>0|[1-9]\d*))?$'
)


def version_file() -> Path:
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return root/'VERSION'


def read_version(path:Path|None=None) -> str:
    source=path or version_file()
    try:value=source.read_text(encoding='ascii').strip()
    except OSError as exc:raise RuntimeError('MovieVault VERSION file is missing or unreadable') from exc
    if not SEMVER_PATTERN.fullmatch(value):
        raise RuntimeError('VERSION must use MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rc.NUMBER')
    return value


def windows_numeric_version(version:str) -> str:
    match=SEMVER_PATTERN.fullmatch(version)
    if not match:raise ValueError('Unsupported MovieVault semantic version')
    parts=[int(match[name]) for name in ('major','minor','patch')]
    revision=int(match.group('rc') or 0)
    if any(part>65535 for part in parts+[revision]):
        raise ValueError('Windows version components must be between 0 and 65535')
    return '.'.join(str(part) for part in parts+[revision])


def filename_version(version:str) -> str:
    if not SEMVER_PATTERN.fullmatch(version):raise ValueError('Unsupported MovieVault semantic version')
    return re.sub(r'[^A-Za-z0-9.-]+','_',version).strip('._')


VERSION=read_version()
WINDOWS_VERSION=windows_numeric_version(VERSION)
ARTIFACT_VERSION=filename_version(VERSION)

"""Opt-in, copy-only migration from MovieVault 1.x into a separate v2 profile.

Never write into the legacy directory or import credentials. The import is staged
as a validated SQLite snapshot and activated on the next cold app start.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

LEGACY_MAX_SCHEMA = 2
STAGE_NAME = 'migration_pending'
REQUIRED_TABLES = {'meta', 'roots', 'movies', 'subtitles', 'settings', 'imdb_titles'}
MAX_DATABASE_BYTES = 3_000_000_000
MAX_ARCHIVE_BYTES = 4_000_000_000

# Only these user preferences may cross the v1 -> v2 trust boundary. Provider
# selections and AI state are reset because their credentials deliberately do not
# migrate. Unknown rows are not carried forward: old releases and local forks may
# have stored credentials in the settings table under arbitrary names.
MIGRATABLE_SETTING_KEYS = frozenset({
    'auto_posters',
    'poster_in_folder',
    'archive_missing',
    'auto_imdb',
    'default_external_subtitle_lang',
    'theme',
    'auto_frame_fallback',
})

# Current v2 settings are safe preferences, not credentials. This wider allowlist
# is used once when cleaning catalogs that were already migrated and may since
# have acquired legitimate v2 provider/model preferences.
CURRENT_V2_SETTING_KEYS = MIGRATABLE_SETTING_KEYS | frozenset({
    'poster_provider',
    'auto_gemini_fallback',
    'gemini_model',
})
SETTINGS_SANITIZED_META_KEY = 'legacy_settings_sanitized'

class MigrationError(Exception):
    pass


def _retain_setting_allowlist(conn: sqlite3.Connection, allowed: frozenset[str]) -> int:
    placeholders=','.join('?' for _ in allowed)
    cursor=conn.execute(f'DELETE FROM settings WHERE key NOT IN ({placeholders})',tuple(sorted(allowed)))
    return max(0,int(cursor.rowcount))


def _sanitize_staged_legacy_database(db_path: Path) -> int:
    """Remove every non-allowlisted v1 setting from a private staged copy."""
    conn=sqlite3.connect(str(db_path))
    try:
        removed=_retain_setting_allowlist(conn,MIGRATABLE_SETTING_KEYS)
        for key,value in {
            'poster_provider':'commons',
            'auto_gemini_fallback':'0',
            'gemini_model':'',
        }.items():
            conn.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,value))
        conn.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',(SETTINGS_SANITIZED_META_KEY,'1'))
        conn.commit()
        return removed
    finally:
        conn.close()


def cleanup_migrated_v2_database(db_path: str|Path) -> int:
    """One-time cleanup for v2 catalogs activated by older migration code.

    The cleanup is deliberately limited to databases carrying v1_imported_at and
    lacking our completion marker. It never opens or modifies the original v1
    source database.
    """
    path=Path(db_path)
    if not path.is_file() or path.is_symlink():return 0
    conn=sqlite3.connect(str(path),timeout=30)
    try:
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'meta','settings'} <= tables:return 0
        imported=conn.execute("SELECT 1 FROM meta WHERE key='v1_imported_at'").fetchone()
        completed=conn.execute('SELECT 1 FROM meta WHERE key=?',(SETTINGS_SANITIZED_META_KEY,)).fetchone()
        if not imported or completed:return 0
        removed=_retain_setting_allowlist(conn,CURRENT_V2_SETTING_KEYS)
        conn.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',(SETTINGS_SANITIZED_META_KEY,'1'))
        conn.commit()
        return removed
    finally:
        conn.close()


def legacy_data_dir() -> Path:
    # v1.0 stored data outside the source-code folder.
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')/'MovieVault'
    return Path.home()/'.local'/'share'/'MovieVault'


def _inspect_db(db_path: Path) -> dict:
    if not db_path.is_file() or db_path.is_symlink():
        raise MigrationError('A regular MovieVault database file was not found.')
    if db_path.stat().st_size > MAX_DATABASE_BYTES:
        raise MigrationError('The legacy database is larger than the configured safety limit.')
    try:
        conn = sqlite3.connect(f'{db_path.resolve().as_uri()}?mode=ro', uri=True, timeout=15)
        try:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise MigrationError('The legacy database failed SQLite integrity_check.')
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise MigrationError('The selected database does not have the expected v1 MovieVault tables.')
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            schema = int(row[0]) if row else 1
            if schema > LEGACY_MAX_SCHEMA or schema < 1:
                raise MigrationError(f'Unsupported source schema: {schema}')
            counts = {t: int(conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]) for t in ('roots', 'movies', 'subtitles', 'imdb_titles')}
            counts['schema'] = schema
            return counts
        finally:
            conn.close()
    except (sqlite3.DatabaseError, ValueError, OSError) as exc:
        raise MigrationError('Could not validate legacy MovieVault database.') from exc


def _zip_members(z: zipfile.ZipFile) -> list[str]:
    members=z.infolist()
    if len(members) > 60000 or sum(i.file_size for i in members)>MAX_ARCHIVE_BYTES:
        raise MigrationError('Backup ZIP is too large to import safely.')
    names=[]
    for item in members:
        name=item.filename
        if name not in ('movievault.sqlite','manifest.json') and not re.fullmatch(r'posters/\d+\.jpg',name):
            raise MigrationError('Backup contains an unexpected entry.')
        if item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:
            raise MigrationError('Backup contains an unsafe entry.')
        if item.compress_size and item.file_size/max(1,item.compress_size)>400 and item.file_size>10_000_000:
            raise MigrationError('Suspicious ZIP compression ratio.')
        names.append(name)
    if not {'manifest.json','movievault.sqlite'} <= set(names):
        raise MigrationError('Not a valid MovieVault backup ZIP.')
    try:
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('product')!='MovieVault' or int(manifest.get('schema',999))>LEGACY_MAX_SCHEMA:
            raise MigrationError('Backup manifest does not identify a supported MovieVault version.')
    except (ValueError,KeyError,TypeError) as exc:
        raise MigrationError('Invalid legacy backup manifest.') from exc
    return names


def resolve_legacy_source(selected: str|Path|None = None) -> dict:
    path=Path(selected).expanduser().resolve() if selected else legacy_data_dir().resolve()
    if path.is_file() and path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            names=_zip_members(z)
            with tempfile.TemporaryDirectory() as tmp:
                db=Path(tmp)/'movievault.sqlite'
                with z.open('movievault.sqlite') as src, db.open('wb') as dest:
                    shutil.copyfileobj(src,dest,1024*1024)
                info=_inspect_db(db)
        return dict(info, source=str(path), kind='backup_zip', posters=sum(bool(re.fullmatch(r'posters/\d+\.jpg',n)) for n in names))
    if path.is_file() and path.name.lower()=='movievault.sqlite':
        info=_inspect_db(path)
        poster_dir=path.parent/'posters'
        return dict(info,source=str(path),kind='database',posters=len(list(poster_dir.glob('[0-9]*.jpg'))) if poster_dir.is_dir() else 0)
    if path.is_dir():
        candidates=(path/'movievault.sqlite',path/'data'/'movievault.sqlite',path/'MovieVault'/'movievault.sqlite')
        database=next((p for p in candidates if p.is_file()),None)
        if database is None:
            legacy=legacy_data_dir()
            # The user may select their old Desktop/MovieVault_v1 application folder.
            # v1 kept its real database in LOCALAPPDATA, not in source files.
            if any((path/exe).is_file() for exe in ('MovieVault.pyw','MovieVault.exe','mv_server.py')) and (legacy/'movievault.sqlite').is_file():
                result=resolve_legacy_source(legacy)
                result['selected_folder']=str(path)
                result['notice']='The selected folder contains the old application; the actual v1 data was found automatically in the Windows user profile.'
                return result
            hint=(f' The v1 database usually lives in {legacy}, not the old program folder.'
                  ' Use Auto-detect Previous Library instead.')
            raise MigrationError('No v1 database found in the selected folder.'+hint)
        result=resolve_legacy_source(database)
        result['selected_folder']=str(path)
        return result
    raise MigrationError('Select a previous MovieVault data folder, movievault.sqlite or backup ZIP.')


def _snapshot_source(info:dict, dest:Path) -> None:
    source=Path(info['source'])
    poster_dir=None
    if info['kind']=='backup_zip':
        with zipfile.ZipFile(source) as z:
            _zip_members(z)
            with z.open('movievault.sqlite') as db, (dest/'movievault.sqlite').open('wb') as out:
                shutil.copyfileobj(db,out,1024*1024)
            for name in z.namelist():
                if re.fullmatch(r'posters/\d+\.jpg',name):
                    target=dest/name;target.parent.mkdir(exist_ok=True)
                    with z.open(name) as src,target.open('wb') as out:shutil.copyfileobj(src,out,1024*1024)
    else:
        src=sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro',uri=True,timeout=30)
        out=sqlite3.connect(str(dest/'movievault.sqlite'))
        try:src.backup(out,pages=512,sleep=0.05)
        finally:out.close();src.close()
        poster_dir=source.parent/'posters'
        if poster_dir.is_dir() and not poster_dir.is_symlink():
            (dest/'posters').mkdir(exist_ok=True)
            for p in poster_dir.iterdir():
                if p.is_file() and not p.is_symlink() and re.fullmatch(r'\d+\.jpg',p.name) and p.stat().st_size<=12_000_000:
                    shutil.copyfile(p,dest/'posters'/p.name)
    _inspect_db(dest/'movievault.sqlite')
    # Licensed TMDb images are not permanent portable content. Never export the token.
    db=sqlite3.connect(str(dest/'movievault.sqlite'))
    try:
        # Staging is moved as one SQLite file. Force a checkpointed rollback journal
        # BEFORE any changes, never leave critical updates only in a -wal sidecar.
        db.execute('PRAGMA journal_mode=DELETE')
        old_tmdb=db.execute("SELECT id FROM movies WHERE poster_source='TMDb'").fetchall()
        for (movie_id,) in old_tmdb:
            (dest/'posters'/f'{movie_id}.jpg').unlink(missing_ok=True)
            db.execute("UPDATE movies SET poster_path='',poster_source='',poster_credit='',poster_attempted_at='' WHERE id=?",(movie_id,))
        # Provider credentials deliberately stay on the old account/profile. An
        # explicit allowlist prevents any legacy/extension credential row from
        # crossing into the staged v2 database or its future backups.
        _retain_setting_allowlist(db,MIGRATABLE_SETTING_KEYS)
        for key,value in {
            'poster_provider':'commons',
            'auto_gemini_fallback':'0',
            'gemini_model':'',
        }.items():
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,value))
        db.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',(SETTINGS_SANITIZED_META_KEY,'1'))
        db.commit()
    finally:
        db.close()
    if any((dest/('movievault.sqlite'+suffix)).exists() for suffix in ('-wal','-shm')):
        raise MigrationError('SQLite import snapshot has unexpected journal sidecar files.')
    _inspect_db(dest/'movievault.sqlite')


def _target_is_empty(target:Path) -> bool:
    db_path=target/'movievault.sqlite'
    if not db_path.is_file():return True
    try:
        con=sqlite3.connect(f'{db_path.resolve().as_uri()}?mode=ro',uri=True)
        try:
            return all(con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]==0 for t in ('movies','imdb_titles','roots','subtitles'))
        finally:con.close()
    except sqlite3.DatabaseError:return False


def stage_migration(selected:str|Path|None, target_dir:str|Path) ->dict:
    target=Path(target_dir).expanduser().resolve();target.mkdir(parents=True,exist_ok=True)
    if (target/'restore_pending.zip').exists():raise MigrationError('A v2 restore is already staged. Complete or cancel it before importing v1.')
    if not _target_is_empty(target):raise MigrationError('The new library already contains data. Use Restore or a separate v2 profile; no automatic overwrite is allowed.')
    pending=target/STAGE_NAME
    if pending.exists():raise MigrationError('A previous import is already staged. Restart MovieVault before trying another import.')
    info=resolve_legacy_source(selected)
    if Path(info['source']).resolve()==(target/'movievault.sqlite').resolve():raise MigrationError('The source and destination database cannot be the same.')
    with tempfile.TemporaryDirectory(prefix='mv-migrate-',dir=target) as tmp:
        d=Path(tmp)
        _snapshot_source(info,d)
        staged=_inspect_db(d/'movievault.sqlite')
        if any(staged[t]!=info[t] for t in ('movies','imdb_titles','subtitles','roots')):
            raise MigrationError('Source data changed during migration; please close v1 and try again.')
        manifest={'source_type':info['kind'],'created':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                  'counts':{k:staged[k] for k in ('movies','imdb_titles','subtitles','roots')},'no_credentials':True}
        (d/'migration.json').write_text(json.dumps(manifest),encoding='utf8')
        # Atomic staging, leaving the live database completely untouched.
        os.replace(d,pending)
    return {'staged':True,'counts':manifest['counts'],'restart_required':True,
            'message':'Import snapshot is ready. Restart MovieVault to activate it; the v1 library was not modified.'}


def apply_pending_migration(target_dir:str|Path) ->bool:
    target=Path(target_dir).expanduser().resolve();pending=target/STAGE_NAME
    if not pending.is_dir():return False
    manifest=json.loads((pending/'migration.json').read_text(encoding='utf8'))
    # A pending directory may have been produced by a vulnerable earlier build.
    # Sanitize the private staged copy before it can replace the live v2 catalog.
    _sanitize_staged_legacy_database(pending/'movievault.sqlite')
    info=_inspect_db(pending/'movievault.sqlite')
    if any(info[k]!=manifest['counts'][k] for k in ('movies','imdb_titles','roots','subtitles')):
        raise MigrationError('Pending import did not pass final integrity checks.')
    if not _target_is_empty(target):
        raise MigrationError('Current v2 library is no longer empty. Refusing to replace it with the previous library.')
    # There can be a new empty v2 DB (created on the first run). Preserve a safe copy.
    db=target/'movievault.sqlite';backupdir=target/'backups';backupdir.mkdir(exist_ok=True)
    if db.is_file():
        backup=backupdir/('Before_Legacy_Import_'+time.strftime('%Y%m%d_%H%M%S')+'.sqlite')
        source=sqlite3.connect(str(db));out=sqlite3.connect(str(backup))
        try:source.backup(out)
        finally:source.close();out.close()
    for suffix in ('-wal','-shm'):(target/('movievault.sqlite'+suffix)).unlink(missing_ok=True)
    os.replace(pending/'movievault.sqlite',db)
    targetposters=target/'posters';targetposters.mkdir(exist_ok=True)
    for p in (pending/'posters').glob('*.jpg') if (pending/'posters').is_dir() else ():
        if re.fullmatch(r'\d+\.jpg',p.name) and not p.is_symlink():os.replace(p,targetposters/p.name)
    con=sqlite3.connect(str(db))
    try:
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('v1_imported_at',?)",(time.strftime('%Y-%m-%dT%H:%M:%S%z'),))
        con.commit()
    finally:
        con.close()
    shutil.rmtree(pending)
    return True

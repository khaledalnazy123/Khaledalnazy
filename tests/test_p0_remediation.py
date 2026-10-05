import io
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from mv_core import BACKUP_REQUIRED_TABLES,Catalog,ValidationError
from mv_migration import (
    CURRENT_V2_SETTING_KEYS,
    MIGRATABLE_SETTING_KEYS,
    SETTINGS_SANITIZED_META_KEY,
    apply_pending_migration,
    stage_migration,
)


class P0RemediationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def movie(self,catalog,title,filename='movie.mkv'):
        root=self.base/(title.replace(' ','_')+'_films');root.mkdir(exist_ok=True)
        with catalog.connect() as db:
            root_id=db.execute('INSERT INTO roots(path) VALUES(?)',(str(root),)).lastrowid
            return db.execute(
                '''INSERT INTO movies(root_id,relative_path,original_filename,current_filename,
                   display_title,added_at,last_seen,manual_fields)
                   VALUES(?,?,?,?,?,?,?,?)''',
                (root_id,filename,filename,filename,title,'2026','2026','[]'),
            ).lastrowid

    def poster(self,color):
        output=io.BytesIO();Image.new('RGB',(80,120),color).save(output,'PNG')
        return output.getvalue()

    def settings(self,database):
        with sqlite3.connect(str(database)) as db:
            return dict(db.execute('SELECT key,value FROM settings'))

    def test_migration_setting_allowlist_preserves_source_and_excludes_secrets(self):
        legacy=Catalog(self.base/'legacy');target=Catalog(self.base/'target')
        with legacy.connect() as db:
            db.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
            db.executemany('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',[
                ('theme','midnight'),('auto_imdb','0'),('poster_provider','tmdb'),
                ('auto_gemini_fallback','1'),('gemini_model','legacy-model'),
                ('tmdb_token','SYNTHETIC_TOKEN'),('api_key','SYNTHETIC_KEY'),
                ('client_secret','SYNTHETIC_SECRET'),('extension_preference','keep-me-out'),
            ])
        source_before=legacy.db.read_bytes()

        stage_migration(legacy.dir,target.dir)
        staged_settings=self.settings(target.dir/'migration_pending'/'movievault.sqlite')
        self.assertEqual(set(staged_settings),set(MIGRATABLE_SETTING_KEYS)|{
            'poster_provider','auto_gemini_fallback','gemini_model'
        })
        self.assertEqual(staged_settings['theme'],'midnight')
        self.assertEqual(staged_settings['auto_imdb'],'0')
        self.assertEqual(staged_settings['poster_provider'],'commons')
        self.assertEqual(staged_settings['auto_gemini_fallback'],'0')
        self.assertEqual(staged_settings['gemini_model'],'')
        self.assertEqual(legacy.db.read_bytes(),source_before)
        self.assertEqual(self.settings(legacy.db)['tmdb_token'],'SYNTHETIC_TOKEN')

        self.assertTrue(apply_pending_migration(target.dir))
        imported=Catalog(target.dir)
        imported_settings=imported.settings()
        self.assertNotIn('tmdb_token',imported_settings)
        self.assertNotIn('api_key',imported_settings)
        self.assertNotIn('client_secret',imported_settings)
        self.assertNotIn('extension_preference',imported_settings)

    def test_activation_resanitizes_pending_snapshot_from_an_older_build(self):
        legacy=Catalog(self.base/'legacy');target=Catalog(self.base/'target')
        with legacy.connect() as db:db.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
        stage_migration(legacy.dir,target.dir)
        pending_db=target.dir/'migration_pending'/'movievault.sqlite'
        with sqlite3.connect(str(pending_db)) as db:
            db.execute('DELETE FROM meta WHERE key=?',(SETTINGS_SANITIZED_META_KEY,))
            db.execute("INSERT INTO settings(key,value) VALUES('legacy_api_token','SYNTHETIC_SECRET')")
            db.commit()
        self.assertTrue(apply_pending_migration(target.dir))
        self.assertNotIn('legacy_api_token',Catalog(target.dir).settings())

    def test_already_migrated_catalog_is_cleaned_before_backup(self):
        data=self.base/'already_migrated';catalog=Catalog(data)
        with catalog.connect() as db:
            db.execute("INSERT INTO meta(key,value) VALUES('v1_imported_at','2026-10-01')")
            db.executemany('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',[
                ('theme','light'),('poster_provider','none'),
                ('tmdb_token','SYNTHETIC_TOKEN'),('password','SYNTHETIC_PASSWORD'),
                ('unknown_legacy_setting','value'),
            ])

        reopened=Catalog(data)
        cleaned=reopened.settings()
        self.assertEqual(cleaned['theme'],'light')
        self.assertEqual(cleaned['poster_provider'],'none')
        self.assertTrue(set(cleaned)<=set(CURRENT_V2_SETTING_KEYS))
        self.assertNotIn('tmdb_token',cleaned)
        self.assertNotIn('password',cleaned)
        self.assertNotIn('unknown_legacy_setting',cleaned)
        with reopened.connect() as db:
            self.assertEqual(db.execute('SELECT value FROM meta WHERE key=?',(SETTINGS_SANITIZED_META_KEY,)).fetchone()[0],'1')

        backup=Path(reopened.backup(self.base/'cleaned-backup.zip'))
        with zipfile.ZipFile(backup) as archive,tempfile.TemporaryDirectory() as td:
            database=Path(td)/'movievault.sqlite';database.write_bytes(archive.read('movievault.sqlite'))
            backup_settings=self.settings(database)
        self.assertTrue(set(backup_settings)<=set(CURRENT_V2_SETTING_KEYS))

    def test_corrupt_or_structurally_invalid_database_never_reaches_pending(self):
        catalog=Catalog(self.base/'live')
        corrupt=self.base/'corrupt.zip'
        with zipfile.ZipFile(corrupt,'w') as archive:
            archive.writestr('manifest.json',json.dumps({'product':'MovieVault','schema':3}))
            archive.writestr('movievault.sqlite',b'not a sqlite database')
        with self.assertRaisesRegex(ValidationError,'database is corrupt or unreadable'):
            catalog.stage_restore(corrupt)
        self.assertFalse((catalog.dir/'restore_pending.zip').exists())

        incomplete_db=self.base/'incomplete.sqlite'
        with sqlite3.connect(str(incomplete_db)) as db:
            db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
            db.execute("INSERT INTO meta VALUES('schema_version','3')")
        incomplete=self.base/'incomplete.zip'
        with zipfile.ZipFile(incomplete,'w') as archive:
            archive.writestr('manifest.json',json.dumps({'product':'MovieVault','schema':3}))
            archive.write(incomplete_db,'movievault.sqlite')
        with self.assertRaisesRegex(ValidationError,'missing required tables'):
            catalog.stage_restore(incomplete)
        self.assertFalse((catalog.dir/'restore_pending.zip').exists())

    def test_integrity_valid_database_with_missing_core_columns_never_reaches_pending(self):
        source=Catalog(self.base/'structural-source')
        malformed_db=self.base/'missing-columns.sqlite'
        with source.connect() as live,sqlite3.connect(str(malformed_db)) as output:
            live.backup(output)
        with sqlite3.connect(str(malformed_db)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('ALTER TABLE movies RENAME TO movies_complete')
            db.execute('CREATE TABLE movies(id INTEGER PRIMARY KEY)')
            db.execute('DROP TABLE movies_complete')
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue(BACKUP_REQUIRED_TABLES <= tables)
        malformed=self.base/'missing-columns.zip'
        with zipfile.ZipFile(malformed,'w') as archive:
            archive.writestr('manifest.json',json.dumps({'product':'MovieVault','schema':3}))
            archive.write(malformed_db,'movievault.sqlite')

        live=Catalog(self.base/'structural-live')
        with self.assertRaisesRegex(ValidationError,'movies is missing required columns'):
            live.stage_restore(malformed)
        self.assertFalse((live.dir/'restore_pending.zip').exists())

    def test_restored_v1_derived_catalog_is_sanitized_before_becoming_active(self):
        vulnerable=Catalog(self.base/'vulnerable-backup');self.movie(vulnerable,'Restored Movie')
        with vulnerable.connect() as db:
            db.execute("INSERT INTO meta(key,value) VALUES('v1_imported_at','2026-09-01')")
            db.execute('DELETE FROM meta WHERE key=?',(SETTINGS_SANITIZED_META_KEY,))
            db.executemany('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',[
                ('theme','light'),
                ('tmdb_token','SYNTHETIC_RESTORED_TOKEN'),
                ('legacy_api_key','SYNTHETIC_RESTORED_KEY'),
                ('client_secret','SYNTHETIC_RESTORED_SECRET'),
            ])
        restore=Path(vulnerable.backup(self.base/'vulnerable.zip'))

        live=Catalog(self.base/'restore-target');self.movie(live,'Live Movie')
        live.stage_restore(restore)
        self.assertTrue(live.process_pending_restore())

        active=live.settings()
        self.assertEqual(active['theme'],'light')
        self.assertNotIn('tmdb_token',active)
        self.assertNotIn('legacy_api_key',active)
        self.assertNotIn('client_secret',active)
        with live.connect() as db:
            marker=db.execute('SELECT value FROM meta WHERE key=?',(SETTINGS_SANITIZED_META_KEY,)).fetchone()
        self.assertEqual(marker['value'],'1')

    def test_crc_failure_never_reaches_pending(self):
        source=Catalog(self.base/'source');original=Path(source.backup(self.base/'original.zip'))
        damaged=self.base/'damaged-crc.zip'
        with zipfile.ZipFile(original) as incoming,zipfile.ZipFile(damaged,'w',compression=zipfile.ZIP_STORED) as outgoing:
            for info in incoming.infolist():outgoing.writestr(info.filename,incoming.read(info.filename))
        with zipfile.ZipFile(damaged) as archive:
            info=archive.getinfo('movievault.sqlite')
            data_offset=info.header_offset
        with damaged.open('r+b') as stream:
            stream.seek(data_offset);header=stream.read(30)
            name_length,extra_length=struct.unpack('<HH',header[26:30])
            stream.seek(data_offset+30+name_length+extra_length+100)
            byte=stream.read(1);stream.seek(-1,1);stream.write(bytes([byte[0]^0x01]))

        live=Catalog(self.base/'live')
        with self.assertRaisesRegex(ValidationError,'CRC'):
            live.stage_restore(damaged)
        self.assertFalse((live.dir/'restore_pending.zip').exists())

    def test_corrupted_staged_database_is_quarantined_and_live_catalog_survives(self):
        source=Catalog(self.base/'source');self.movie(source,'Restored Movie')
        valid=Path(source.backup(self.base/'valid.zip'))
        live=Catalog(self.base/'live');live_id=self.movie(live,'Live Movie')
        live.stage_restore(valid)
        pending=live.dir/'restore_pending.zip'
        with zipfile.ZipFile(pending,'w') as archive:
            archive.writestr('manifest.json',json.dumps({'product':'MovieVault','schema':3}))
            archive.writestr('movievault.sqlite',b'corrupted after staging')

        self.assertFalse(live.process_pending_restore())
        self.assertFalse(pending.exists())
        self.assertEqual(live.movie(live_id)['display_title'],'Live Movie')
        self.assertEqual(len(list((live.dir/'restore_quarantine').glob('restore_failed_*.zip'))),1)
        reopened=Catalog(live.dir)
        self.assertEqual(reopened.movie(live_id)['display_title'],'Live Movie')
        events=[json.loads(line) for line in reopened.diagnostics.path.read_text(encoding='utf8').splitlines()]
        recovery=[event for event in events if event['event']=='restore_activation_recovered'][-1]
        self.assertEqual(recovery['failure_type'],'ValidationError')
        self.assertTrue(recovery['quarantined'])
        self.assertNotIn('message',recovery)
        self.assertNotIn('path',recovery)

    def test_activation_fault_rolls_back_database_and_posters_then_quarantines(self):
        source=Catalog(self.base/'source');source.set_settings({'poster_in_folder':'0'})
        source_id=self.movie(source,'Restored Movie')
        source.set_poster(source_id,self.poster('red'))
        restore=Path(source.backup(self.base/'restore.zip'))

        live=Catalog(self.base/'live');live.set_settings({'poster_in_folder':'0'})
        live_id=self.movie(live,'Live Movie')
        live.set_poster(live_id,self.poster('blue'))
        live_poster=live.poster_bytes(live_id)
        live.stage_restore(restore)

        real_replace=__import__('os').replace
        state={'database_replaced':False,'fault_injected':False}
        def fail_during_poster_activation(source_path,destination_path):
            source_path=Path(source_path);destination_path=Path(destination_path)
            if destination_path==live.db and source_path.name=='movievault.sqlite':
                state['database_replaced']=True
            if destination_path==live.posters and source_path.name=='posters' and state['database_replaced']:
                state['fault_injected']=True
                raise OSError('synthetic poster activation failure')
            return real_replace(source_path,destination_path)

        with patch('mv_core.os.replace',side_effect=fail_during_poster_activation):
            self.assertFalse(live.process_pending_restore())
        self.assertTrue(state['database_replaced'])
        self.assertTrue(state['fault_injected'])
        self.assertEqual(live.movie(live_id)['display_title'],'Live Movie')
        self.assertEqual(live.poster_bytes(live_id),live_poster)
        self.assertFalse((live.dir/'restore_pending.zip').exists())
        self.assertEqual(len(list((live.dir/'restore_quarantine').glob('restore_failed_*.zip'))),1)
        reopened=Catalog(live.dir)
        self.assertEqual(reopened.movie(live_id)['display_title'],'Live Movie')
        self.assertEqual(reopened.poster_bytes(live_id),live_poster)


if __name__=='__main__':unittest.main(verbosity=2)

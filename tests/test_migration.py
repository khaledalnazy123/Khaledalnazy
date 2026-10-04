import io
import json
import zipfile
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog
from mv_migration import (MigrationError,resolve_legacy_source,stage_migration,apply_pending_migration)

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.legacy=Catalog(self.base/'legacy');self.new=Catalog(self.base/'v2')
        with self.legacy.connect() as c:
            c.execute("INSERT INTO roots(path) VALUES(?)",(str(self.base/'movies'),))
            c.execute("""INSERT INTO movies(root_id,relative_path,original_filename,current_filename,display_title,added_at,last_seen,manual_fields,notes,poster_path,poster_source,poster_locked)
                    VALUES(1,'movie.mkv','My Original Movie.mkv','movie.mkv','My Edited Title','2026','2026','[\"display_title\"]','test note','posters/1.jpg','Manual',1)""")
            c.execute("INSERT INTO subtitles(movie_id,kind,filename,format,language,source,quality) VALUES(1,'external','arabic.srt','SRT','Arabic','OSN','Excellent')")
            c.execute("INSERT INTO imdb_titles VALUES(?,?,?,?,?,?)",('tt1111111','my movie','My Movie',2020,'Drama',90))
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('imdb_imported_at','2026-10-02')")
            c.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
        i=io.BytesIO();Image.new('RGB',(90,130),'blue').save(i,'JPEG')
        (self.legacy.posters/'1.jpg').write_bytes(i.getvalue())
        (self.legacy.dir/'tmdb_token.protected').write_text('SECRET DO NOT IMPORT')
    def test_preview_staging_activation_does_not_mutate_source(self):
        before=self.legacy.db.read_bytes()
        info=resolve_legacy_source(self.legacy.dir)
        self.assertEqual((info['movies'],info['imdb_titles'],info['subtitles']),(1,1,1))
        staged=stage_migration(self.legacy.dir,self.new.dir)
        self.assertTrue(staged['restart_required'])
        self.assertEqual(self.new.stats()['total'],0)
        self.assertTrue(apply_pending_migration(self.new.dir))
        imported=Catalog(self.new.dir)
        self.assertEqual(imported.stats()['total'],1)
        self.assertEqual(imported.movie(1)['original_filename'],'My Original Movie.mkv')
        self.assertEqual(imported.movie(1)['display_title'],'My Edited Title')
        self.assertEqual(imported.movie(1)['subtitles'][0]['source'],'OSN')
        self.assertIsNotNone(imported.stats()['imdb_imported_at'])
        self.assertEqual(imported.poster_bytes(1),(self.legacy.posters/'1.jpg').read_bytes())
        self.assertEqual(before,self.legacy.db.read_bytes())
        self.assertFalse((self.new.dir/'tmdb_token.protected').exists())
        self.assertTrue(list((self.new.dir/'backups').glob('Before_Legacy_Import_*.sqlite')))
    def test_no_overwrite_of_populated_v2(self):
        with self.new.connect() as c:c.execute("INSERT INTO roots(path) VALUES('/some/folder')")
        with self.assertRaisesRegex(MigrationError,'already contains data'):
            stage_migration(self.legacy.dir,self.new.dir)
    def test_program_folder_with_no_database_explains_actual_location(self):
        source=self.base/'MovieVault_v1';source.mkdir()
        with self.assertRaisesRegex(MigrationError,'database usually lives'):
            resolve_legacy_source(source)
    def test_selecting_old_application_folder_auto_follows_user_data(self):
        from unittest.mock import patch
        source=self.base/'MovieVault_v1';source.mkdir()
        (source/'MovieVault.pyw').write_text('# old application launcher')
        with patch('mv_migration.legacy_data_dir', return_value=self.legacy.dir):
            data=resolve_legacy_source(source)
        self.assertEqual(data['movies'],1)
        self.assertIn('actual v1 data',data['notice'])
        self.assertEqual(data['source'],str(self.legacy.db.resolve()))

    def test_backup_zip_as_source(self):
        # Create a legacy-compatible backup manifest (schema 2).
        generated=Path(self.legacy.backup());archive=self.base/'legacy-export.zip'
        with zipfile.ZipFile(generated) as zin,zipfile.ZipFile(archive,'w') as zout:
            for f in zin.infolist():
                blob=zin.read(f.filename)
                if f.filename=='manifest.json':
                    manifest=json.loads(blob);manifest['schema']=2;blob=json.dumps(manifest).encode()
                zout.writestr(f.filename,blob)
        info=resolve_legacy_source(archive)
        self.assertEqual(info['imdb_titles'],1)
        self.assertEqual(info['posters'],1)
        self.assertTrue(stage_migration(archive,self.new.dir)['staged'])
        self.assertTrue(apply_pending_migration(self.new.dir))
        self.assertEqual(Catalog(self.new.dir).stats()['total'],1)
    def test_reject_unsupported_schema_and_bad_zip(self):
        with self.legacy.connect() as c:c.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
        with self.assertRaisesRegex(MigrationError,'Unsupported source schema'):
            resolve_legacy_source(self.legacy.dir)

if __name__=='__main__':unittest.main()

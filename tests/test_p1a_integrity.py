import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mv_core import Catalog,SCHEMA_VERSION,file_content_sha256,file_fingerprint


class P1ALibraryIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def catalog(self,name):
        catalog=Catalog(self.base/name)
        catalog.set_settings({'auto_posters':'0','poster_in_folder':'0'})
        return catalog

    def movie(self,catalog,title,filename='movie.mkv'):
        root=self.base/(catalog.dir.name+'_'+title.replace(' ','_'))
        root.mkdir(exist_ok=True)
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

    def scan(self,catalog,root_id):
        job={'cancel':False,'total':0,'done':0,'message':''}
        with patch('mv_core.probe_media',return_value={'streams':[],'format':{}}):
            result=catalog._scan_impl(job,[root_id])
        return result

    def test_restore_with_zero_archived_posters_clears_omitted_tmdb_and_stale_generation(self):
        source=self.catalog('source-zero');source_id=self.movie(source,'Restored Movie')
        source.set_poster(source_id,self.poster('red'))
        with source.connect() as db:
            db.execute("UPDATE movies SET poster_source='TMDb',poster_locked=0 WHERE id=?",(source_id,))
        backup=Path(source.backup(self.base/'zero-posters.zip'))
        with zipfile.ZipFile(backup) as archive:
            self.assertFalse(any(name.startswith('posters/') for name in archive.namelist()))

        live=self.catalog('live-zero');live_id=self.movie(live,'Previous Movie')
        self.assertEqual(source_id,live_id,'The regression requires overlapping numeric movie IDs')
        live.set_poster(live_id,self.poster('blue'))
        (live.posters/'999.jpg').write_bytes(self.poster('green'))

        live.stage_restore(backup)
        self.assertTrue(live.process_pending_restore())
        restored=live.movie(source_id)
        self.assertEqual(restored['display_title'],'Restored Movie')
        self.assertEqual(restored['poster_path'],'')
        self.assertEqual(restored['poster_source'],'')
        self.assertIsNone(live.poster_bytes(source_id))
        self.assertEqual(list(live.posters.iterdir()),[])

    def test_restore_preserves_archived_manual_poster_and_removes_previous_generation(self):
        source=self.catalog('source-manual');source_id=self.movie(source,'Manual Poster Movie')
        source.set_poster(source_id,self.poster('red'));source_poster=source.poster_bytes(source_id)
        backup=Path(source.backup(self.base/'manual-poster.zip'))
        with zipfile.ZipFile(backup) as archive:
            self.assertIn(f'posters/{source_id}.jpg',archive.namelist())

        live=self.catalog('live-manual');live_id=self.movie(live,'Previous Movie')
        stale_id=self.movie(live,'Unrelated Previous Movie','other.mkv')
        self.assertEqual(source_id,live_id)
        live.set_poster(live_id,self.poster('blue'))
        live.set_poster(stale_id,self.poster('green'))

        live.stage_restore(backup)
        self.assertTrue(live.process_pending_restore())
        self.assertEqual(live.poster_bytes(source_id),source_poster)
        self.assertEqual([path.name for path in live.posters.iterdir()],[f'{source_id}.jpg'])

    def test_restore_upgrades_older_v2_additive_schema_before_same_instance_scan(self):
        media_root=self.base/'older_v2_media';media_root.mkdir()
        media=media_root/'Older Backup Movie (2024).mkv';media.write_bytes(b'older-v2-media'*30000)
        source=self.catalog('source-older-v2')
        root_id=source.add_root(media_root)['id'];self.scan(source,root_id)
        current_backup=Path(source.backup(self.base/'current-schema.zip'))

        older_db=self.base/'older-v2.sqlite'
        with zipfile.ZipFile(current_backup) as archive:
            older_db.write_bytes(archive.read('movievault.sqlite'))
        with sqlite3.connect(older_db) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('ALTER TABLE movies DROP COLUMN content_sha256')
        with sqlite3.connect(older_db) as db:
            columns={row[1] for row in db.execute('PRAGMA table_info(movies)')}
        self.assertNotIn('content_sha256',columns)

        older_backup=self.base/'older-v2-backup.zip'
        with zipfile.ZipFile(current_backup) as source_archive,zipfile.ZipFile(older_backup,'w',zipfile.ZIP_DEFLATED) as output:
            for info in source_archive.infolist():
                data=older_db.read_bytes() if info.filename=='movievault.sqlite' else source_archive.read(info)
                output.writestr(info,data)

        live=self.catalog('live-older-v2')
        live.stage_restore(older_backup)
        self.assertTrue(live.process_pending_restore())
        with live.connect() as db:
            restored_columns={row['name'] for row in db.execute('PRAGMA table_info(movies)')}
            before=db.execute('SELECT content_sha256 FROM movies').fetchone()['content_sha256']
        self.assertIn('content_sha256',restored_columns)
        self.assertEqual(before,'')

        result=self.scan(live,root_id)
        self.assertEqual(result['failed_files'],0)
        with live.connect() as db:
            digest=db.execute('SELECT content_sha256 FROM movies').fetchone()['content_sha256']
        self.assertEqual(digest,file_content_sha256(media))

    def test_restored_older_schema_is_normalized_before_same_instance_rebackup(self):
        source=self.catalog('source-older-schema');movie_id=self.movie(source,'Older Schema Movie')
        current_backup=Path(source.backup(self.base/'current-version.zip'))
        older_db=self.base/'schema-2.sqlite'
        with zipfile.ZipFile(current_backup) as archive:
            older_db.write_bytes(archive.read('movievault.sqlite'))
        with sqlite3.connect(older_db) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute("UPDATE meta SET value='2' WHERE key='schema_version'")

        older_backup=self.base/'schema-2-backup.zip'
        with zipfile.ZipFile(current_backup) as source_archive,zipfile.ZipFile(older_backup,'w',zipfile.ZIP_DEFLATED) as output:
            for info in source_archive.infolist():
                if info.filename=='movievault.sqlite':data=older_db.read_bytes()
                elif info.filename=='manifest.json':
                    manifest=json.loads(source_archive.read(info));manifest['schema']=2
                    data=json.dumps(manifest,separators=(',',':')).encode('utf8')
                else:data=source_archive.read(info)
                output.writestr(info,data)

        live=self.catalog('live-older-schema')
        self.assertEqual(live.validate_backup(older_backup)['manifest']['schema'],2)
        live.stage_restore(older_backup)
        self.assertTrue(live.process_pending_restore())
        self.assertEqual(live.movie(movie_id)['display_title'],'Older Schema Movie')
        with live.connect() as db:
            schema=db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()['value']
        self.assertEqual(schema,str(SCHEMA_VERSION))

        same_instance_backup=Path(live.backup(self.base/'same-instance-current.zip'))
        self.assertEqual(live.validate_backup(same_instance_backup)['manifest']['schema'],SCHEMA_VERSION)
        live.stage_restore(same_instance_backup)
        self.assertTrue(live.process_pending_restore())
        self.assertEqual(live.movie(movie_id)['display_title'],'Older Schema Movie')

    def test_scan_continues_when_discovered_file_disappears_before_stat(self):
        catalog=self.catalog('scan-disappears');root=self.base/'scan_disappears_movies';root.mkdir()
        victim=root/'Victim (2020).mkv';survivor=root/'Survivor (2021).mkv'
        victim.write_bytes(b'v'*300000);survivor.write_bytes(b's'*300000)
        root_id=catalog.add_root(root)['id'];self.scan(catalog,root_id)
        rows={item['display_title']:item['id'] for item in catalog.movies(limit=10)['items']}
        victim_id=rows['Victim'];survivor_id=rows['Survivor']

        real_walk=os.walk
        def disappearing_walk(*args,**kwargs):
            for base,dirs,files in real_walk(*args,**kwargs):
                if victim.name in files:victim.unlink()
                yield base,dirs,files

        with patch('mv_core.os.walk',new=disappearing_walk):
            result=self.scan(catalog,root_id)
        self.assertEqual(result['failed_files'],1)
        self.assertEqual(catalog.movie(victim_id)['status'],'available')
        self.assertEqual(catalog.movie(survivor_id)['status'],'available')
        with catalog.connect() as db:
            status=db.execute('SELECT last_status FROM roots WHERE id=?',(root_id,)).fetchone()['last_status']
        self.assertEqual(status,'scan_partial')
        events=[json.loads(line) for line in catalog.diagnostics.path.read_text(encoding='utf8').splitlines()]
        skipped=[event for event in events if event['event']=='scan_file_skipped'][-1]
        self.assertEqual((skipped['root_id'],skipped['phase'],skipped['failure_type']),(root_id,'stat','FileNotFoundError'))
        self.assertNotIn('path',skipped);self.assertNotIn('filename',skipped)

    def test_scan_continues_when_existing_file_becomes_inaccessible_before_fingerprint(self):
        catalog=self.catalog('scan-inaccessible');root=self.base/'scan_inaccessible_movies';root.mkdir()
        victim=root/'Blocked (2022).mkv';survivor=root/'Still Here (2023).mkv'
        victim.write_bytes(b'b'*300000);survivor.write_bytes(b'h'*300000)
        root_id=catalog.add_root(root)['id'];self.scan(catalog,root_id)
        rows={item['display_title']:item['id'] for item in catalog.movies(limit=10)['items']}
        victim_id=rows['Blocked'];survivor_id=rows['Still Here']
        stat=victim.stat();os.utime(victim,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000_000))
        real_fingerprint=file_fingerprint
        def inaccessible_fingerprint(path):
            if path==victim:raise PermissionError('synthetic access loss')
            return real_fingerprint(path)

        with patch('mv_core.file_fingerprint',side_effect=inaccessible_fingerprint):
            result=self.scan(catalog,root_id)
        self.assertEqual(result['failed_files'],1)
        self.assertEqual(catalog.movie(victim_id)['status'],'available')
        self.assertEqual(catalog.movie(survivor_id)['status'],'available')
        events=[json.loads(line) for line in catalog.diagnostics.path.read_text(encoding='utf8').splitlines()]
        skipped=[event for event in events if event['event']=='scan_file_skipped'][-1]
        self.assertEqual((skipped['phase'],skipped['failure_type']),('sampled_fingerprint','PermissionError'))

    def test_sampled_fingerprint_collision_does_not_relink_different_media(self):
        catalog=self.catalog('collision');root=self.base/'collision_movies';root.mkdir()
        first=root/'First Identity (2001).mkv';first.write_bytes(b'\0'*1_000_000)
        root_id=catalog.add_root(root)['id'];self.scan(catalog,root_id)
        original=catalog.movies(limit=10)['items'][0];original_id=original['id']
        catalog.patch_movie(original_id,{'display_title':'Manual First Identity','notes':'preserve this metadata'})
        first_sample=file_fingerprint(first);first_full=file_content_sha256(first)
        first.unlink()

        second=root/'Second Identity (2022).mkv'
        changed=bytearray(1_000_000);changed[200000]=1;second.write_bytes(changed)
        second_before=hashlib.sha256(second.read_bytes()).hexdigest()
        self.assertEqual(file_fingerprint(second),first_sample)
        self.assertNotEqual(file_content_sha256(second),first_full)

        result=self.scan(catalog,root_id)
        self.assertEqual(result['added'],1)
        self.assertEqual(catalog.movies(limit=10)['total'],2)
        old=catalog.movie(original_id)
        self.assertEqual(old['status'],'missing')
        self.assertEqual(old['display_title'],'Manual First Identity')
        self.assertEqual(old['notes'],'preserve this metadata')
        new=next(catalog.movie(item['id']) for item in catalog.movies(limit=10)['items'] if item['id']!=original_id)
        self.assertEqual(new['status'],'available')
        self.assertEqual(new['original_filename'],second.name)
        self.assertEqual(new['display_title'],'Second Identity')
        self.assertEqual(new['notes'],'')
        self.assertEqual(hashlib.sha256(second.read_bytes()).hexdigest(),second_before)


if __name__=='__main__':unittest.main(verbosity=2)

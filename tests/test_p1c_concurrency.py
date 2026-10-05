import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import mv_core
from mv_core import BusyError,Catalog,ValidationError


class P1CConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.catalog=Catalog(self.base/'data')
        self.catalog.set_settings({'auto_posters':'0','poster_in_folder':'0'})
        root=self.base/'movies';root.mkdir();self.video=root/'Race Movie (2020).mkv';self.video.write_bytes(b'movie')
        with self.catalog.connect() as db:
            root_id=db.execute('INSERT INTO roots(path) VALUES(?)',(str(root),)).lastrowid
            self.mid=db.execute(
                '''INSERT INTO movies(root_id,relative_path,original_filename,current_filename,
                   display_title,year,status,added_at,last_seen,manual_fields)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (root_id,self.video.name,self.video.name,self.video.name,'Race Movie',2020,'available','2026','2026','[]'),
            ).lastrowid

    def image(self,color):
        output=io.BytesIO();Image.new('RGB',(90,140),color).save(output,'PNG');return output.getvalue()

    def wait_job(self,job_id,timeout=5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            job=self.catalog.job(job_id)
            if job['state']!='running':return job
            time.sleep(.005)
        self.fail('Timed out waiting for job completion')

    def blocking_tmdb(self,reached,release,poster):
        class Client:
            def __init__(self,_token):pass
            def match(self,*_args):
                reached.set()
                if not release.wait(5):raise TimeoutError('test release timeout')
                return {'id':77,'poster_path':'/poster.jpg','release_date':'2020-01-01'},'title_year'
            def download_poster(self,_path):return poster
        return Client

    def test_manual_poster_wins_over_inflight_automatic_fetch(self):
        reached=threading.Event();release=threading.Event();done=threading.Event();errors=[]
        client=self.blocking_tmdb(reached,release,self.image('blue'))
        def automatic():
            try:self.catalog._tmdb_poster(self.mid,{},replace=True)
            except Exception as exc:errors.append(exc)
            finally:done.set()
        with patch('mv_core.TMDbClient',client):
            worker=threading.Thread(target=automatic);worker.start()
            self.assertTrue(reached.wait(5))
            self.catalog.set_poster(self.mid,self.image('red'),credit='manual-newest')
            release.set();self.assertTrue(done.wait(5));worker.join()
        movie=self.catalog.movie(self.mid)
        self.assertEqual(movie['poster_source'],'manual upload');self.assertEqual(movie['poster_credit'],'manual-newest')
        self.assertEqual(movie['poster_locked'],1);self.assertTrue(any(isinstance(exc,ValidationError) for exc in errors))

    def test_two_poster_writers_publish_complete_matching_generation(self):
        barrier=threading.Barrier(3);errors=[]
        def writer(color,label):
            try:
                barrier.wait();self.catalog.set_poster(self.mid,self.image(color),credit=label)
            except Exception as exc:errors.append(exc)
        threads=[threading.Thread(target=writer,args=('red','red')),threading.Thread(target=writer,args=('blue','blue'))]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(5)
        self.assertFalse(errors)
        movie=self.catalog.movie(self.mid);poster=self.catalog.poster_bytes(self.mid)
        with Image.open(io.BytesIO(poster)) as image:pixel=image.convert('RGB').resize((1,1)).getpixel((0,0))
        dominant='red' if pixel[0]>pixel[2] else 'blue'
        self.assertEqual(movie['poster_credit'],dominant)
        self.assertFalse(list(self.catalog.posters.glob('*.partial')))

    def test_clear_poster_wins_over_inflight_background_fetch(self):
        self.catalog.set_poster(self.mid,self.image('green'),source='Wikimedia Commons')
        reached=threading.Event();release=threading.Event();done=threading.Event()
        client=self.blocking_tmdb(reached,release,self.image('blue'))
        def automatic():
            try:self.catalog._tmdb_poster(self.mid,{},replace=True)
            except ValidationError:pass
            finally:done.set()
        with patch('mv_core.TMDbClient',client):
            worker=threading.Thread(target=automatic);worker.start()
            self.assertTrue(reached.wait(5));self.assertTrue(self.catalog.clear_poster(self.mid))
            release.set();self.assertTrue(done.wait(5));worker.join()
        movie=self.catalog.movie(self.mid)
        self.assertEqual(movie['poster_path'],'');self.assertEqual(movie['poster_source'],'')
        self.assertIsNone(self.catalog.poster_bytes(self.mid));self.assertFalse((self.catalog.posters/f'{self.mid}.jpg').exists())

    def test_manual_metadata_edit_wins_over_running_refresh(self):
        reached=threading.Event();release=threading.Event()
        class Client:
            def __init__(self,_token):pass
            def match(self,*_args):
                reached.set()
                if not release.wait(5):raise TimeoutError('test release timeout')
                return {'id':42,'release_date':'2020-01-01'},'title_year'
            def details(self,_mid):
                return {'release_date':'2020-01-01','overview':'fresh','vote_average':8.1,
                        'external_ids':{'imdb_id':'tt1111111'},'credits':{'cast':[]}}
        with patch('mv_core.TMDbClient',Client):
            job_id=self.catalog.refresh_movie_details(self.mid)
            self.assertTrue(reached.wait(5))
            self.catalog.patch_movie(self.mid,{'display_title':'Manual Title','year':2033,'imdb_id':'tt9999999'})
            release.set();job=self.wait_job(job_id)
        self.assertEqual(job['state'],'completed',job['message'])
        movie=self.catalog.movie(self.mid)
        self.assertEqual((movie['display_title'],movie['year'],movie['imdb_id']),('Manual Title',2033,'tt9999999'))
        self.assertEqual(movie['overview'],'');self.assertIsNone(movie['tmdb_id'])
        self.assertTrue(job['result']['stale'])

    def test_simultaneous_exclusive_job_starts_allow_exactly_one(self):
        barrier=threading.Barrier(3);release=threading.Event();started=threading.Event();results=[]
        def work(_job):started.set();release.wait(5);return {'ok':True}
        def starter():
            barrier.wait()
            try:results.append(('started',self.catalog.start_job('race',work)))
            except BusyError:results.append(('busy',None))
        threads=[threading.Thread(target=starter),threading.Thread(target=starter)]
        for thread in threads:thread.start()
        barrier.wait();self.assertTrue(started.wait(5))
        for thread in threads:thread.join(5)
        try:self.assertEqual(sorted(kind for kind,_ in results),['busy','started'])
        finally:release.set()
        job_id=next(value for kind,value in results if kind=='started')
        self.assertEqual(self.wait_job(job_id)['state'],'completed')

    def test_cancelled_job_releases_slot_and_does_not_cancel_next_job(self):
        reached=threading.Event();release=threading.Event()
        def first(_job):
            reached.set()
            if not release.wait(5):raise TimeoutError('test release timeout')
            return {'first':True}
        first_id=self.catalog.start_job('first',first);self.assertTrue(reached.wait(5))
        self.catalog.cancel_job(first_id);release.set()
        first_job=self.wait_job(first_id);self.assertEqual(first_job['state'],'cancelled')
        second_id=self.catalog.start_job('second',lambda job:{'cancel_seen':bool(job.get('cancel'))})
        second_job=self.wait_job(second_id)
        self.assertEqual(second_job['state'],'completed');self.assertEqual(second_job['result'],{'cancel_seen':False})
        self.assertNotEqual(first_id,second_id);self.assertIsNone(self.catalog.active_job)

    def test_failed_job_releases_slot_for_immediate_successor(self):
        def fail(_job):raise RuntimeError('synthetic failure')
        failed=self.wait_job(self.catalog.start_job('failure',fail))
        self.assertEqual(failed['state'],'failed');self.assertFalse(failed['commit_completed'])
        successor=self.wait_job(self.catalog.start_job('successor',lambda _job:'ok'))
        self.assertEqual(successor['state'],'completed');self.assertEqual(successor['result'],'ok')
        self.assertIsNone(self.catalog.active_job)

    def test_backup_rejected_during_unsafe_poster_commit(self):
        reached=threading.Event();release=threading.Event();done=threading.Event();errors=[]
        real_replace=os.replace;destination=self.catalog.posters/f'{self.mid}.jpg'
        def blocking_replace(source,target):
            if Path(target)==destination and Path(source).suffix=='.partial':
                reached.set()
                if not release.wait(5):raise TimeoutError('test release timeout')
            return real_replace(source,target)
        def writer():
            try:self.catalog.set_poster(self.mid,self.image('purple'))
            except Exception as exc:errors.append(exc)
            finally:done.set()
        with patch('mv_core.os.replace',side_effect=blocking_replace):
            worker=threading.Thread(target=writer);worker.start()
            self.assertTrue(reached.wait(5))
            with self.assertRaisesRegex(BusyError,'artwork is being updated'):
                self.catalog.backup(self.base/'during-poster.zip')
            release.set();self.assertTrue(done.wait(5));worker.join()
        self.assertFalse(errors);self.assertTrue(self.catalog.poster_bytes(self.mid))
        self.assertFalse((self.base/'during-poster.zip').exists())


if __name__=='__main__':unittest.main(verbosity=2)

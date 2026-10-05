import gzip
import io
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mv_core import Catalog,parse_filename


class BlockingText:
    def __init__(self,text,reached,release,block_after=4):
        self.lines=iter(io.StringIO(text));self.reached=reached;self.release=release
        self.block_after=block_after;self.count=0
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def __iter__(self):return self
    def __next__(self):
        line=next(self.lines);self.count+=1
        if self.count==self.block_after:
            self.reached.set()
            if not self.release.wait(5):raise TimeoutError('test release timeout')
        return line


class BlockingDownload:
    def __init__(self,reached,release):
        self.reached=reached;self.release=release;self.read_count=0
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def geturl(self):return 'https://datasets.imdbws.com/title.ratings.tsv.gz'
    def read(self,_size):
        self.read_count+=1
        if self.read_count==1:return b'first download chunk'
        if self.read_count==2:
            self.reached.set()
            if not self.release.wait(5):raise TimeoutError('test release timeout')
            return b'second download chunk'
        return b''


class P1BCorrectnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.catalog=Catalog(self.base/'data')
        self.catalog.set_settings({'auto_posters':'0','poster_in_folder':'0'})

    def wait_job(self,job_id,timeout=8):
        deadline=time.time()+timeout
        while time.time()<deadline:
            job=self.catalog.job(job_id)
            if job['state']!='running':return job
            time.sleep(.01)
        self.fail('Timed out waiting for background job')

    def movie(self,title='Identity Test',year=2020):
        root=self.base/'movies';root.mkdir(exist_ok=True)
        with self.catalog.connect() as db:
            row=db.execute('SELECT id FROM roots WHERE path=?',(str(root),)).fetchone()
            root_id=row['id'] if row else db.execute('INSERT INTO roots(path) VALUES(?)',(str(root),)).lastrowid
            return db.execute(
                '''INSERT INTO movies(root_id,relative_path,original_filename,current_filename,
                   display_title,year,added_at,last_seen,manual_fields)
                   VALUES(?,?,?,?,?,?,?,?,?)''',
                (root_id,'identity.mkv','identity.mkv','identity.mkv',title,year,'2026','2026','[]'),
            ).lastrowid

    def seed_identity_case(self,movie_id):
        with self.catalog.connect() as db:
            db.execute('INSERT INTO imdb_titles VALUES(?,?,?,?,?,?)',('tt1111111','identity test','Identity Test',2020,'Drama',100))
            db.executemany('INSERT INTO imdb_ratings VALUES(?,?,?)',[
                ('tt1111111',9.9,9000),('tt2222222',4.2,4200),
            ])
        self.catalog.patch_movie(movie_id,{'imdb_id':'tt2222222'})

    def test_title_import_cancellation_keeps_live_index_and_removes_stage(self):
        with self.catalog.connect() as db:
            db.execute('INSERT INTO imdb_titles VALUES(?,?,?,?,?,?)',('tt9000000','sentinel','Sentinel',2000,'Drama',90))
        text='tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n'
        text+=''.join(f'tt{i:07d}\tmovie\tMovie {i}\tMovie {i}\t0\t2020\t\\N\t100\tDrama\n' for i in range(1,10))
        source=self.base/'title.basics.tsv.gz';source.write_bytes(b'fixture')
        reached=threading.Event();release=threading.Event()
        with patch('mv_core.gzip.open',return_value=BlockingText(text,reached,release)):
            job_id=self.catalog.import_imdb(source)
            self.assertTrue(reached.wait(5));self.assertTrue(self.catalog.cancel_job(job_id)['accepted']);release.set()
            job=self.wait_job(job_id)
        self.assertEqual(job['state'],'cancelled');self.assertFalse(job['commit_completed'])
        self.assertEqual(job['result'],{'cancelled':True,'committed':False})
        with self.catalog.connect() as db:
            rows=[tuple(row) for row in db.execute('SELECT tconst,primary_title FROM imdb_titles')]
        self.assertEqual(rows,[('tt9000000','Sentinel')])
        self.assertFalse((self.catalog.dir/'imdb_stage.sqlite').exists())
        self.assertNotIn(str(self.base),job['message'])

    def test_ratings_import_cancellation_keeps_live_index_and_removes_stage(self):
        with self.catalog.connect() as db:
            db.execute('INSERT INTO imdb_ratings VALUES(?,?,?)',('tt9000000',6.5,100))
        text='tconst\taverageRating\tnumVotes\n'+''.join(f'tt{i:07d}\t8.0\t100\n' for i in range(1,10))
        source=self.base/'title.ratings.tsv.gz';source.write_bytes(b'fixture')
        reached=threading.Event();release=threading.Event()
        with patch('mv_core.gzip.open',return_value=BlockingText(text,reached,release)):
            job_id=self.catalog.import_imdb_ratings(source)
            self.assertTrue(reached.wait(5));self.catalog.cancel_job(job_id);release.set()
            job=self.wait_job(job_id)
        self.assertEqual(job['state'],'cancelled');self.assertFalse(job['commit_completed'])
        with self.catalog.connect() as db:
            rows=[tuple(row) for row in db.execute('SELECT * FROM imdb_ratings')]
        self.assertEqual(rows,[('tt9000000',6.5,100)])
        self.assertFalse((self.catalog.dir/'imdb_ratings_stage.sqlite').exists())

    def test_ratings_download_cancellation_removes_files_and_never_imports(self):
        with self.catalog.connect() as db:
            db.execute('INSERT INTO imdb_ratings VALUES(?,?,?)',('tt9000000',6.5,100))
        reached=threading.Event();release=threading.Event();response=BlockingDownload(reached,release)
        with patch('mv_core.urllib.request.urlopen',return_value=response),patch.object(self.catalog,'_imdb_ratings_import_impl') as importer:
            job_id=self.catalog.download_imdb_ratings()
            self.assertTrue(reached.wait(5));self.catalog.cancel_job(job_id);release.set()
            job=self.wait_job(job_id)
        self.assertEqual(job['state'],'cancelled');self.assertFalse(job['commit_completed']);importer.assert_not_called()
        self.assertFalse((self.catalog.dir/'title.ratings.partial').exists())
        self.assertFalse((self.catalog.dir/'title.ratings.tsv.gz').exists())
        with self.catalog.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM imdb_ratings').fetchone()),('tt9000000',6.5,100))

    def test_cancel_after_atomic_title_commit_reports_completed(self):
        source=self.base/'title.basics.tsv.gz'
        with gzip.open(source,'wt',encoding='utf8') as output:
            output.write('tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n')
            output.write('tt1234567\tmovie\tCommitted Movie\tCommitted Movie\t0\t2020\t\\N\t100\tDrama\n')
        reached=threading.Event();release=threading.Event()
        def hold_after_commit(_job):
            reached.set()
            if not release.wait(5):raise TimeoutError('test release timeout')
            return 0
        with patch.object(self.catalog,'_enrich_existing_movies',side_effect=hold_after_commit):
            job_id=self.catalog.import_imdb(source)
            self.assertTrue(reached.wait(5));self.catalog.cancel_job(job_id);release.set()
            job=self.wait_job(job_id)
        self.assertEqual(job['state'],'completed');self.assertTrue(job['commit_completed'])
        self.assertEqual(job['result']['titles_imported'],1)
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('SELECT tconst FROM imdb_titles').fetchone()['tconst'],'tt1234567')
        self.assertFalse((self.catalog.dir/'imdb_stage.sqlite').exists())

    def test_locked_imdb_id_controls_manual_and_local_refresh_ratings(self):
        movie_id=self.movie();self.seed_identity_case(movie_id)
        matched=self.catalog.match_imdb(movie_id);movie=self.catalog.movie(movie_id)
        self.assertEqual(matched['candidate_imdb_id'],'tt1111111')
        self.assertEqual((movie['imdb_id'],movie['imdb_rating']),('tt2222222',4.2))

        with self.catalog.connect() as db:db.execute('UPDATE movies SET imdb_rating=NULL WHERE id=?',(movie_id,))
        self.catalog._refresh_local_metadata({'cancel':False})
        self.assertEqual((self.catalog.movie(movie_id)['imdb_id'],self.catalog.movie(movie_id)['imdb_rating']),('tt2222222',4.2))
        with self.catalog.connect() as db:db.execute('UPDATE movies SET imdb_rating=NULL WHERE id=?',(movie_id,))
        self.catalog._enrich_existing_movies({'cancel':False,'message':''})
        self.assertEqual((self.catalog.movie(movie_id)['imdb_id'],self.catalog.movie(movie_id)['imdb_rating']),('tt2222222',4.2))

        ratings=self.base/'title.ratings.tsv.gz'
        with gzip.open(ratings,'wt',encoding='utf8') as output:
            output.write('tconst\taverageRating\tnumVotes\n')
            output.write('tt1111111\t9.8\t9800\n')
            output.write('tt2222222\t4.3\t4300\n')
        imported=self.wait_job(self.catalog.import_imdb_ratings(ratings))
        self.assertEqual(imported['state'],'completed')
        self.assertEqual((self.catalog.movie(movie_id)['imdb_id'],self.catalog.movie(movie_id)['imdb_rating']),('tt2222222',4.3))

    def test_locked_imdb_id_controls_scan_and_tmdb_refresh_ratings(self):
        root=self.base/'scan_movies';root.mkdir();media=root/'Identity Test (2020).mkv';media.write_bytes(b'media'*50000)
        root_id=self.catalog.add_root(root)['id']
        job={'cancel':False,'total':0,'done':0,'message':''}
        with patch('mv_core.probe_media',return_value={'streams':[],'format':{}}):self.catalog._scan_impl(job,[root_id])
        movie_id=self.catalog.movies()['items'][0]['id'];self.seed_identity_case(movie_id)
        self.catalog.set_settings({'auto_imdb':'1'});media.write_bytes(media.read_bytes()+b'changed')
        with patch('mv_core.probe_media',return_value={'streams':[],'format':{}}):self.catalog._scan_impl(job,[root_id])
        self.assertEqual((self.catalog.movie(movie_id)['imdb_id'],self.catalog.movie(movie_id)['imdb_rating']),('tt2222222',4.2))

        details={'id':10,'title':'Identity Test','release_date':'2020-01-01','external_ids':{'imdb_id':'tt1111111'},'credits':{'cast':[]}}
        with patch('mv_core.TMDbClient') as client:
            client.return_value.match.return_value=({'id':10,'title':'Identity Test','release_date':'2020-01-01'},'title_year')
            client.return_value.details.return_value=details
            result=self.wait_job(self.catalog.refresh_movie_details(movie_id))
        self.assertEqual(result['state'],'completed')
        self.assertEqual((self.catalog.movie(movie_id)['imdb_id'],self.catalog.movie(movie_id)['imdb_rating']),('tt2222222',4.2))

    def test_unlocked_movie_uses_exact_imdb_match_and_rating(self):
        movie_id=self.movie()
        with self.catalog.connect() as db:
            db.execute('INSERT INTO imdb_titles VALUES(?,?,?,?,?,?)',('tt1111111','identity test','Identity Test',2020,'Drama',100))
            db.execute('INSERT INTO imdb_ratings VALUES(?,?,?)',('tt1111111',9.9,9000))
        result=self.catalog.match_imdb(movie_id);movie=self.catalog.movie(movie_id)
        self.assertTrue(result['matched'])
        self.assertEqual((movie['imdb_id'],movie['imdb_rating']),('tt1111111',9.9))

    def test_year_leading_filename_regression_corpus(self):
        cases={
            '1917 (2019).mkv':('1917',2019,'','',''),
            '2001 A Space Odyssey (1968).mkv':('2001 A Space Odyssey',1968,'','',''),
            '1984.mkv':('1984',None,'','',''),
            'Ordinary Title (2020).mkv':('Ordinary Title',2020,'','',''),
            '1984 (1956) 2020 Remaster.mkv':('1984',1956,'','',''),
            'Ordinary.Title.2020.1080p.BluRay-YTS.mkv':('Ordinary Title',2020,'1080p','BluRay','YTS'),
            'No.Year.Movie.WEB-DL-QXR.mkv':('No Year Movie',None,'','WEB-DL','QXR'),
        }
        for filename,expected in cases.items():
            with self.subTest(filename=filename):
                parsed=parse_filename(filename)
                self.assertEqual((parsed['title'],parsed['year'],parsed['resolution_tag'],parsed['source'],parsed['release_group']),expected)


if __name__=='__main__':unittest.main(verbosity=2)

import io,json,sys,tempfile,time,unittest,zipfile
from pathlib import Path
from email.message import Message
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_tmdb import TMDbClient,TMDbError,CredentialStore,_SameHostRedirect
from mv_core import Catalog,ValidationError

class Reply(io.BytesIO):
    def __init__(self,b,ctype='application/json'):
        super().__init__(b);self.headers=Message();self.headers['Content-Type']=ctype
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class TMDBTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.cat=Catalog(Path(self.t.name)/'app');self.cat.set_settings({'auto_posters':'0','poster_in_folder':'1'})
        root=Path(self.t.name)/'movies';root.mkdir();self.video=root/'Brick (2025) [1080p] [YTS].mkv';self.video.write_bytes(b'fake-movie'*200)
        rid=self.cat.add_root(root)['id'];job=self.cat.scan([rid])
        for _ in range(300):
            if self.cat.job(job)['state']!='running':break
            time.sleep(.01)
        self.mid=self.cat.movies()['items'][0]['id'];self.token='a'*65+'.'+'b'*75
    def fake(self,req,timeout=0):
        url=req.full_url
        if '/configuration' in url:payload={'images':{'secure_base_url':'https://image.tmdb.org/t/p/'}}
        elif '/find/tt' in url:payload={'movie_results':[{'id':100,'title':'Brick','release_date':'2025-07-10','poster_path':'/abc123.jpg'}]}
        elif '/search/movie' in url:payload={'results':[{'id':100,'title':'Brick','original_title':'Brick','release_date':'2025-07-10','poster_path':'/abc123.jpg'}]}
        elif url.startswith('https://image.tmdb.org/'):
            b=io.BytesIO();Image.new('RGB',(200,300),(3,4,5)).save(b,'JPEG');return Reply(b.getvalue(),'image/jpeg')
        else:raise AssertionError('Unexpected external URL '+url)
        self.assertIn('Bearer ',req.get_header('Authorization'))
        return Reply(json.dumps(payload).encode())
    def connect(self):
        with patch('mv_tmdb.open_trusted',side_effect=self.fake):self.assertTrue(self.cat.connect_tmdb(self.token)['connected'])
    def test_connect_reuse_and_no_exposure(self):
        with self.cat.connect() as c:c.execute("UPDATE movies SET poster_attempted_at='previous commons failure' WHERE id=?",(self.mid,))
        self.connect()
        self.assertEqual(self.cat.settings()['poster_provider'],'tmdb')
        self.assertEqual(self.cat.movie(self.mid)['poster_attempted_at'],'')
        self.assertNotIn(self.token,json.dumps(self.cat.tmdb_status()))
        self.assertNotIn(self.token,self.cat.db.read_bytes().decode('latin1'))
        self.assertEqual(self.cat.tmdb_credentials.get(),self.token)
    def test_fetch_online_tmdb_then_preserve_manual(self):
        self.connect()
        with patch('mv_tmdb.open_trusted',side_effect=self.fake):
            result=self.cat._online_poster(self.mid,{},False)
        self.assertEqual(result['tmdb_id'],100)
        self.assertEqual(self.cat.movie(self.mid)['poster_source'],'TMDb')
        self.assertTrue(self.cat.poster_bytes(self.mid))
        self.assertFalse((self.video.parent/'poster.jpg').exists())
        with self.cat.connect() as c:c.execute('UPDATE movies SET poster_locked=1 WHERE id=?',(self.mid,))
        with patch('mv_tmdb.open_trusted',side_effect=self.fake):
            with self.assertRaisesRegex(ValidationError,'Poster locked'):self.cat._online_poster(self.mid,{},True)
    def test_backup_excludes_tmdb_cache_but_keeps_imdb(self):
        self.connect()
        with patch('mv_tmdb.open_trusted',side_effect=self.fake):self.cat._online_poster(self.mid,{},False)
        with self.cat.connect() as c:c.execute("INSERT INTO imdb_titles VALUES('tt1234567','brick','Brick',2025,'Thriller',99)")
        archive=Path(self.cat.backup())
        with zipfile.ZipFile(archive) as z:
            self.assertIn('movievault.sqlite',z.namelist())
            self.assertNotIn(f'posters/{self.mid}.jpg',z.namelist())
            self.assertNotIn('tmdb_credential.dpapi',z.namelist())
    def test_reject_ambiguous_title_year(self):
        client=TMDbClient(self.token)
        duplicates={'results':[{'id':1,'title':'Brick','release_date':'2025-01-01'}, {'id':2,'title':'Brick','release_date':'2025-09-01'}]}
        with patch.object(client,'get',return_value=duplicates):
            with self.assertRaisesRegex(TMDbError,'unique exact'):client.match('Brick',2025)
    def test_by_imdb_id_prioritized(self):
        client=TMDbClient(self.token)
        with patch.object(client,'get',return_value={'movie_results':[{'id':19,'poster_path':'/abc123.jpg'}]}) as mock:
            r,how=client.match('Brick',2025,'tt1234567')
        self.assertEqual(how,'imdb_id');self.assertEqual(r['id'],19)
        self.assertIn('/find/tt1234567',mock.call_args.args[0])
    def test_no_cross_host_redirect(self):
        import urllib.request
        req=urllib.request.Request('https://api.themoviedb.org/3/configuration',headers={'Authorization':'Bearer SECRET'})
        with self.assertRaisesRegex(TMDbError,'cross-host'): _SameHostRedirect().redirect_request(req,None,302,'',{},'https://another-host.example/steal')
    def test_credential_never_plaintext_on_windows(self):
        store=CredentialStore(self.cat.dir)
        with patch('mv_tmdb.sys.platform','win32'),patch('mv_tmdb._protect',side_effect=lambda value,decrypt=False: (value[::-1] if not decrypt else value[::-1])):
            store.save(self.token)
            self.assertNotIn(self.token,store.path.read_bytes().decode('latin1'))
            store._session=None
            self.assertEqual(store.get(),self.token)
            store.clear()
            self.assertFalse(store.path.exists())
    def test_invalid_token_never_saved(self):
        with self.assertRaises(TMDbError):self.cat.tmdb_credentials.save('contains spaces'*9)
        self.assertFalse(self.cat.tmdb_credentials.path.exists())

if __name__=='__main__':unittest.main(verbosity=2)

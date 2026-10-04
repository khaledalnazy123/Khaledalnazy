import sys,tempfile,unittest,shutil,time,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog
from mv_gemini import GeminiCredentials,GeminiClient, GeminiError

class AiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.base=Path(self.tmp.name);self.cat=Catalog(self.base/'db');self.cat.set_settings({'auto_posters':'0','auto_imdb':'0'})
  self.root=self.base/'films';self.root.mkdir()
  shutil.copyfile(Path(__file__).parent/'assets/sample.mkv',self.root/'Dont Look Up (2021).mkv')
  rid=self.cat.add_root(self.root)['id'];self.wait(self.cat.scan([rid]));self.mid=self.cat.movies()['items'][0]['id']
 def wait(self,jid):
  for _ in range(200):
   x=self.cat.job(jid)
   if x['state']!='running':self.assertEqual(x['state'],'completed',x['message']);return x['result']
   time.sleep(.05)
  self.fail('timeout')
 def setup_keys(self):
  # Unit tests never call real provider network endpoints.
  self.cat.gemini_credentials._session='fakeGeminiKey_abcdefghijklmnopqrstuvwxyz'
  self.cat.tmdb_credentials._session='fakeTMDBKeyabcdefghijklmnopqrstuvwxyz'
  with self.cat.connect() as c:c.execute("INSERT OR REPLACE INTO settings VALUES('gemini_model','gemini-3.6-flash')")
 def test_gemini_title_is_updated_only_after_independent_verification(self):
  self.setup_keys();guess={'title':"Don't Look Up",'year':2021,'imdb_id':'tt11286314','uncertain':False,'reason':'Correct apostrophe'}
  match={'id':900,'title':"Don't Look Up",'original_title':"Don't Look Up",'release_date':'2021-12-24'}
  details={'id':900,'external_ids':{'imdb_id':'tt11286314'}}
  with patch('mv_core.GeminiClient') as gem,patch('mv_core.TMDbClient') as tmdb:
   gem.return_value.identify.return_value=guess
   tmdb.return_value.match.return_value=(match,'imdb_id')
   tmdb.return_value.details.return_value=details
   result=self.wait(self.cat.resolve_ai(self.mid))
  self.assertTrue(result['verified'])
  record=self.cat.movie(self.mid)
  self.assertEqual(record['display_title'],"Don't Look Up")
  self.assertEqual(record['imdb_id'],'tt11286314')
  self.assertEqual(record['original_filename'],'Dont Look Up (2021).mkv')
 def test_wrong_imdb_id_does_not_write_unverified_info(self):
  self.setup_keys();old=self.cat.movie(self.mid)['display_title']
  with patch('mv_core.GeminiClient') as gem,patch('mv_core.TMDbClient') as tmdb:
   gem.return_value.identify.return_value={'title':"Don't Look Up",'year':2021,'imdb_id':'tt1111111','uncertain':False,'reason':'suggestion'}
   tmdb.return_value.match.return_value=({'id':900,'title':"Don't Look Up",'original_title':"Don't Look Up",'release_date':'2021-12-24'},'title_year')
   tmdb.return_value.details.return_value={'id':900,'external_ids':{'imdb_id':'tt11286314'}}
   result=self.wait(self.cat.resolve_ai(self.mid))
  self.assertFalse(result['verified'])
  record=self.cat.movie(self.mid)
  self.assertEqual(record['display_title'],old)
  self.assertEqual(record['imdb_id'],'')
  self.assertEqual(record['ai_suggestion']['status'],'unverified')
 def test_smart_quick_update_preserves_filename_and_notes(self):
  self.cat.patch_movie(self.mid,{'notes':'private note','release_group':'MyGroup'})
  result=self.wait(self.cat.smart_update('quick'))
  self.assertIn('scan',result)
  movie=self.cat.movie(self.mid)
  self.assertEqual(movie['notes'],'private note')
  self.assertEqual(movie['release_group'],'MyGroup')
  self.assertEqual(movie['original_filename'],'Dont Look Up (2021).mkv')
 def test_key_not_persisted_in_dev_mode(self):
  creds=GeminiCredentials(self.base)
  with patch('mv_gemini.sys.platform','linux'):
   creds.save('AIza' + 'A'*35)  # synthetic key shape; never a real credential
  self.assertFalse(creds.path.exists())
  self.assertTrue(creds.get())

if __name__=='__main__':unittest.main()

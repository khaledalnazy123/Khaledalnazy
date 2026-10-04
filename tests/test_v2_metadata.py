import gzip,io,sys,tempfile,unittest,shutil,time
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog

class MetadataTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.base=Path(self.tmp.name);self.cat=Catalog(self.base/'data');self.cat.set_settings({'auto_posters':'0'})
 def wait(self,jid):
  for _ in range(200):
   j=self.cat.job(jid)
   if j['state']!='running':self.assertEqual(j['state'],'completed',j['message']);return j['result']
   time.sleep(.05)
  self.fail('job timeout')
 def film(self):
  root=self.base/'movies';root.mkdir();shutil.copyfile(Path(__file__).parent/'assets/sample.mkv',root/'My Movie (2022) [1080p].mkv')
  self.wait(self.cat.scan([self.cat.add_root(root)['id']]))
  return self.cat.movies()['items'][0]['id']
 def test_imdb_ratings_are_real_official_file_not_tmdb_average(self):
  mid=self.film();self.cat.patch_movie(mid,{'imdb_id':'tt1234567'})
  source=self.base/'title.ratings.tsv.gz'
  with gzip.open(source,'wt',encoding='utf8') as f:f.write('tconst\taverageRating\tnumVotes\ntt1234567\t8.3\t1200\n')
  result=self.wait(self.cat.import_imdb_ratings(source));self.assertEqual(result['ratings_indexed'],1)
  self.assertEqual(self.cat.movie(mid)['imdb_rating'],8.3)
  self.assertIsNotNone(self.cat.stats()['imdb_ratings_at'])
 def test_verified_tmdb_cast_is_separate_from_imdb_rating(self):
  mid=self.film()
  response={'id':101,'title':'My Movie','release_date':'2022-01-01','overview':'An original movie.','vote_average':7.4,
      'external_ids':{'imdb_id':'tt1234567'},'credits':{'cast':[{'name':'Actor One'},{'name':'Actor Two'}]}}
  with patch('mv_core.TMDbClient') as client:
   client.return_value.match.return_value=({'id':101,'title':'My Movie','release_date':'2022-01-01'},'title_year')
   client.return_value.details.return_value=response
   result=self.wait(self.cat.refresh_movie_details(mid))
  film=self.cat.movie(mid)
  self.assertEqual(result['cast_count'],2)
  self.assertEqual(film['cast_names'],'Actor One, Actor Two')
  self.assertEqual(film['tmdb_rating'],7.4)
  self.assertIsNone(film['imdb_rating'])  # never mislabel a TMDB score
  self.assertEqual(self.cat.movies(actor='Actor Two')['total'],1)
 def test_user_generated_frame_poster(self):
  mid=self.film();b=io.BytesIO();Image.new('RGB',(640,360),'#305a86').save(b,'PNG')
  class Proc: returncode=0;stdout=b.getvalue()
  with patch('mv_core.find_ffmpeg',return_value='/fake/ffmpeg'),patch('mv_core.subprocess.run',return_value=Proc()):
   self.wait(self.cat.generate_frame_poster(mid))
  film=self.cat.movie(mid)
  self.assertEqual(film['poster_source'],'Custom Frame')
  self.assertEqual(film['poster_locked'],1)
  self.assertTrue(self.cat.poster_bytes(mid).startswith(b'\xff\xd8'))

if __name__=='__main__':unittest.main()

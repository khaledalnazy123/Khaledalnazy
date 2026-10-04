import sys,io,json,os,time,tempfile,gzip,unittest
from pathlib import Path
from email.message import Message
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog,ValidationError
from PIL import Image

class Response(io.BytesIO):
 def __init__(self,raw,url,mime):
  super().__init__(raw);self._url=url;self.headers=Message();self.headers['Content-Type']=mime;self.headers['Content-Length']=str(len(raw))
 def geturl(self):return self._url
 def __enter__(self):return self
 def __exit__(self,*args):self.close()

class PosterAndImdb(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'films';self.root.mkdir();self.c=Catalog(Path(self.tmp.name)/'app');self.c.set_settings({'auto_posters':'0'})
  self.video=self.root/'The Dark Knight (2008) [1080p] [BluRay] [YTS].mkv';self.video.write_bytes(b'video' * 100)
  root=self.c.add_root(self.root);j=self.c.scan([root['id']]);self.wait(j);self.mid=self.c.movies()['items'][0]['id']
 def tearDown(self):self.tmp.cleanup()
 def wait(self,j):
  for _ in range(200):
   d=self.c.job(j)
   if d['state']!='running':self.assertEqual(d['state'],'completed',d['message']);return d
   time.sleep(.03)
  self.fail('background job not finished')
 def image(self):
  o=io.BytesIO();Image.new('RGB',(100,150),(1,2,3)).save(o,'JPEG');return o.getvalue()
 def commons(self,allowed=True):
  meta={'LicenseShortName':{'value':'CC BY-SA 4.0' if allowed else 'All rights reserved'},'Artist':{'value':'<span>Creative Artist</span>'}}
  d={'query':{'pages':[{'title':'File:The Dark Knight 2008 film poster.jpg','imageinfo':[{'thumburl':'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a8/example.jpg/600px-example.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Example','extmetadata':meta}]}]}}
  return json.dumps(d).encode()
 def test_commons_licensing_and_no_wrong_poster(self):
  def mocked(req,timeout=0):
   url=req.full_url
   return Response(self.commons(),'https://commons.wikimedia.org/w/api.php','application/json') if 'w/api.php' in url else Response(self.image(),url,'image/jpeg')
  with patch('mv_core.urllib.request.urlopen',side_effect=mocked):
   d=self.c._commons_poster(self.mid,{})
  self.assertEqual(d['provider'],'Wikimedia Commons')
  m=self.c.movie(self.mid);self.assertIn('Creative Artist',m['poster_credit']);self.assertEqual(m['poster_source'],'Wikimedia Commons')
  self.assertTrue(self.c.poster_bytes(self.mid));self.assertTrue((self.root/'poster.jpg').exists())
  with patch('mv_core.urllib.request.urlopen',side_effect=mocked):
   with self.assertRaises(ValidationError):self.c._commons_poster(self.mid,{})
 def test_unlicensed_commons_rejected(self):
  def mocked(req,timeout=0):return Response(self.commons(False),'https://commons.wikimedia.org/w/api.php','application/json')
  with patch('mv_core.urllib.request.urlopen',side_effect=mocked):
   with self.assertRaisesRegex(ValidationError,'No confidently matched'):self.c._commons_poster(self.mid,{})
  self.assertFalse(self.c.movie(self.mid)['poster_path'])
 def test_existing_dangling_poster_symlink_never_followed(self):
  if os.name=='nt':self.skipTest('symlink permissions vary on Windows')
  victim=Path(self.tmp.name)/'outside.jpg';local=self.root/'poster.jpg';local.symlink_to(victim)
  self.c.set_poster(self.mid,self.image())
  self.assertFalse(victim.exists());self.assertTrue(local.is_symlink());self.assertTrue(self.c.poster_bytes(self.mid))
 def test_one_click_imdb_and_enrich_existing(self):
  tsv='tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n'+'tt0468569\tmovie\tThe Dark Knight\tThe Dark Knight\t0\t2008\t\\N\t152\tAction,Crime,Drama\n'
  blob=gzip.compress(tsv.encode())
  def fake(req,timeout=0):return Response(blob,'https://datasets.imdbws.com/title.basics.tsv.gz','application/gzip')
  with patch('mv_core.urllib.request.urlopen',side_effect=fake):
   out=self.wait(self.c.download_imdb())
  self.assertEqual(out['result']['titles_imported'],1)
  self.assertEqual(self.c.movie(self.mid)['imdb_id'],'tt0468569')
  self.assertFalse((self.c.dir/'title.basics.tsv.gz').exists())
if __name__=='__main__':unittest.main(verbosity=2)

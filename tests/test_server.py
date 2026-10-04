import io,json,os,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog
from mv_server import MovieServer
from PIL import Image
from unittest.mock import patch

class HttpTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.c=Catalog(Path(self.t.name)/'data');self.c.set_settings({'auto_posters':'0'});self.s=MovieServer(self.c)
  self.thread=threading.Thread(target=self.s.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.s.shutdown();self.s.server_close();self.thread.join(timeout=2);self.t.cleanup()
 def fetch(self,path,method='GET',body=None,token=True):
  headers={'X-MovieVault-Token':self.s.token} if token else {}
  if body is not None:
   if isinstance(body,dict):body=json.dumps(body).encode();headers['Content-Type']='application/json'
   elif isinstance(body,bytes):headers['Content-Type']='image/png'
  req=urllib.request.Request(self.s.url+path.lstrip('/'),method=method,data=body,headers=headers)
  try:
   with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),dict(r.headers)
  except urllib.error.HTTPError as e:return e.code,e.read(),dict(e.headers)
 def test_token_and_endpoints(self):
  status,page,_=self.fetch('/',token=False);self.assertEqual(status,200);self.assertIn(b'MovieVault',page)
  status,body,_=self.fetch('/api/bootstrap',token=False);self.assertEqual(status,400)
  status,body,_=self.fetch('/api/bootstrap');self.assertEqual(status,200);self.assertEqual(json.loads(body)['stats']['total'],0)
  status,body,_=self.fetch('/api/groups');self.assertEqual(json.loads(body)['items'],[])
  status,body,_=self.fetch('/api/settings','POST',{'poster_in_folder':'0'});self.assertEqual(status,200)
  self.assertEqual(json.loads(body)['poster_in_folder'],'0')
 def test_tmdb_token_endpoint_requires_auth_and_does_not_echo_secret(self):
  secret='a'*90
  status,body,_=self.fetch('/api/tmdb/connect','POST',{'read_token':secret},token=False)
  self.assertEqual(status,400)
  with patch('mv_core.TMDbClient.test_connection',return_value=True):
   status,body,_=self.fetch('/api/tmdb/connect','POST',{'read_token':secret})
  self.assertEqual(status,200)
  self.assertTrue(json.loads(body)['connected'])
  self.assertNotIn(secret,body.decode())
  status,body,_=self.fetch('/api/bootstrap')
  self.assertNotIn(secret,body.decode())
  self.assertEqual(json.loads(body)['settings']['poster_provider'],'tmdb')
  status,body,_=self.fetch('/api/tmdb/status')
  self.assertNotIn(secret,body.decode())
  self.assertEqual(status,200)
  status,body,_=self.fetch('/api/tmdb/disconnect','POST',{})
  self.assertEqual(status,200)
  self.assertFalse(json.loads(body)['connected'])
 def test_unauthorized_artwork_and_storage(self):
  folder=Path(self.t.name)/'filmfolder';folder.mkdir()
  root=self.c.add_root(folder)
  # Never allow user-controlled filesystem paths as HTTP static paths.
  status,body,_=self.fetch('/../../mv_core.py',token=False);self.assertEqual(status,400)
  status,body,_=self.fetch('/artwork/999?k=wrong',token=False);self.assertEqual(status,400)
  status,body,_=self.fetch('/api/roots','POST',{'path':str(folder)});self.assertEqual(status,200)
  status,body,_=self.fetch(f'/api/roots/{root["id"]}','DELETE');self.assertEqual(status,200)
  self.assertEqual(self.c.roots(),[])
if __name__=='__main__':unittest.main(verbosity=2)

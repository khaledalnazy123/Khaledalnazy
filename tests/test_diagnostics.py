import json,re,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog

class PrivacyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cat=Catalog(Path(self.tmp.name)/'data')
 def test_export_excludes_credentials_database_and_filename(self):
  self.cat.diagnostics.event('api_request',method='POST',route='/api/tmdb/connect',token='VERYSECRET',message='Bearer SUPERSECRET API_KEY=ALSOSECRET')
  output=Path(self.cat.diagnostics.export(self.cat))
  self.assertTrue(output.is_file())
  with zipfile.ZipFile(output) as z:
   self.assertNotIn('movievault.sqlite',z.namelist())
   self.assertNotIn('tmdb_credential.dpapi',z.namelist())
   raw='\n'.join(z.read(name).decode() for name in z.namelist())
   for secret in ('VERYSECRET','SUPERSECRET','ALSOSECRET'):
    self.assertNotIn(secret,raw)
   self.assertIn('catalog_counts',raw)
 def test_rotation_is_bounded(self):
  # Use the module-level log size as a test fixture.
  from unittest.mock import patch
  with patch('mv_diagnostics.MAX_LOG',300):
   for n in range(50):self.cat.diagnostics.event('test',seq=n,message='more data for a rotating event')
  self.assertLessEqual(len(list(self.cat.diagnostics.folder.glob('events*.jsonl'))),6)

if __name__=='__main__':unittest.main()

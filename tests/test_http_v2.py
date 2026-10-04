"""Integration tests through the bound localhost API; no remote APIs or real movies."""
import json,sys,tempfile,threading,unittest,urllib.request,urllib.error,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog
from mv_server import MovieServer
from mv_migration import resolve_legacy_source

class V2ApiTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name)
        self.cat=Catalog(self.base/'v2');self.cat.set_settings({'auto_posters':'0'})
        self.server=MovieServer(self.cat)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join(2)
    def request(self,path,method='GET',data=None,authenticated=True):
        headers={'Content-Type':'application/json'}
        if authenticated:headers['X-MovieVault-Token']=self.server.token
        body=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(self.server.url+path.lstrip('/'),data=body,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=6) as resp:return resp.status,json.load(resp)
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def test_protected_import_preview_and_stage(self):
        old=Catalog(self.base/'v1')
        with old.connect() as c:
            c.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
            c.execute("INSERT INTO roots(path) VALUES(?)",(str(self.base/'movies'),))
            c.execute("INSERT INTO movies(root_id,relative_path,original_filename,current_filename,display_title,added_at,last_seen) VALUES(1,'film.mkv','film.orig.mkv','film.mkv','Film','2026','2026')")
            c.execute("INSERT INTO imdb_titles VALUES(?,?,?,?,?,?)",('tt0005555','film','Film',2020,'Action',80))
        status,_=self.request('/api/migration/preview','POST',{'path':str(old.dir)},False)
        self.assertEqual(status,400)
        status,preview=self.request('/api/migration/preview','POST',{'path':str(old.dir)})
        self.assertEqual((status,preview['movies'],preview['imdb_titles']),(200,1,1))
        status,staged=self.request('/api/migration/stage','POST',{'path':str(old.dir)})
        self.assertEqual(status,200);self.assertTrue(staged['restart_required'])
        self.assertEqual(self.cat.stats()['total'],0,'Staging must not modify the running v2 DB')
        self.assertEqual(resolve_legacy_source(old.dir)['movies'],1,'Old DB must survive')
        status,err=self.request('/api/migration/stage','POST',{'path':str(old.dir)})
        self.assertEqual(status,400,'Second staging must be rejected')
    def test_update_mode_validated_and_diagnostic_zip(self):
        status,result=self.request('/api/update-all','POST',{'mode':'nonsense','limit':1})
        # Background validation can fail asynchronously; poll until completion.
        self.assertEqual(status,202)
        ident=result['job_id']
        for _ in range(100):
            code,p=self.request('/api/jobs/'+ident)
            if p['state']!='running':break
            time.sleep(.02)
        self.assertEqual(p['state'],'failed')
        status,result=self.request('/api/diagnostics/export','POST',{})
        self.assertEqual(status,200)
        self.assertTrue(Path(result['path']).is_file())

if __name__=='__main__':unittest.main()

import os,sys,tempfile,time,json,gzip,unittest,subprocess,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog,parse_filename,normalize,probe_media,media_summary

class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'movies';self.root.mkdir();self.cat=Catalog(Path(self.tmp.name)/'data');self.cat.set_settings({'auto_posters':'0'})
 def tearDown(self):self.tmp.cleanup()
 def wait(self,job):
  for i in range(200):
   j=self.cat.job(job)
   if j['state']!='running':
    self.assertEqual(j['state'],'completed',j['message']);return j
   time.sleep(.05)
  self.fail('Timed out')
 def sample(self,name='The Dark Knight (2008) [1080p] [BluRay] [5.1] [YTS.GG - YTS.BZ].mkv'):
  d=self.root/'The Dark Knight';d.mkdir(exist_ok=True);p=d/name
  shutil.copyfile(Path(__file__).parent/'assets'/'sample.mkv',p)
  return p
 def test_filename_parser(self):
  d=parse_filename('The Dark Knight (2026) [1080p] [BluRay] [5.1] [YTS.GG - YTS.BZ].mkv')
  self.assertEqual((d['title'],d['year'],d['resolution_tag'],d['release_group'],d['source']),('The Dark Knight',2026,'1080p','YTS','BluRay'))
 def test_scan_edit_rename_archive_relink_and_offline(self):
  fp=self.sample();(fp.parent/'The Dark Knight.en.srt').write_text('1\n00:00:00,000 --> 00:00:00,500\nHello\n')
  root=self.cat.add_root(self.root)
  self.wait(self.cat.scan([root['id']]))
  a=self.cat.movies();self.assertEqual(a['total'],1);id=a['items'][0]['id'];m=self.cat.movie(id)
  self.assertEqual(m['release_group'],'YTS');self.assertEqual(m['original_filename'],fp.name)
  self.assertEqual(m['status'],'available');self.assertEqual(len(m['subtitles']),1)
  self.assertEqual(m['subtitles'][0]['language'],'English');self.assertEqual(m['width'],320)
  self.assertTrue(m['overall_bitrate']>0)
  # New subtitle must appear on Smart Rescan even when video bytes/mtime are unchanged.
  (fp.parent/'Arabic.ar.srt').write_text('1\n00:00:00,000 --> 00:00:00,500\nمرحبا\n',encoding='utf8')
  self.wait(self.cat.scan([root['id']]))
  self.assertEqual(len(self.cat.movie(id)['subtitles']),2)
  self.assertIn('Arabic',[sub['language'] for sub in self.cat.movie(id)['subtitles']])
  self.cat.patch_movie(id,{'display_title':'My Batman Film','release_group':'MYGROUP','subtitle_source':'OSN','translation_quality':'Excellent','notes':'Great archive'})
  new=fp.with_name('MyBatmanRenamed.mkv');fp.rename(new)
  self.wait(self.cat.scan([root['id']]))
  m=self.cat.movie(id);self.assertEqual(self.cat.movies()['total'],1)
  self.assertEqual(m['original_filename'],fp.name);self.assertEqual(m['current_filename'],new.name)
  self.assertEqual(m['release_group'],'MYGROUP');self.assertEqual(m['display_title'],'My Batman Film');self.assertEqual(m['subtitle_source'],'OSN')
  # Offline drive is not the same as a deletion.
  offline=self.root.with_name('movies_disconnected');self.root.rename(offline)
  self.wait(self.cat.scan([root['id']]))
  self.assertEqual(self.cat.movie(id)['status'],'offline')
  offline.rename(self.root)
  self.wait(self.cat.scan([root['id']]))
  self.assertEqual(self.cat.movie(id)['status'],'available')
  new.unlink();self.wait(self.cat.scan([root['id']]))
  self.assertEqual(self.cat.movie(id)['status'],'missing');self.assertEqual(self.cat.movie(id)['original_filename'],fp.name)
 def test_backup_restore(self):
  fp=self.sample();root=self.cat.add_root(self.root);self.wait(self.cat.scan([root['id']]))
  mid=self.cat.movies()['items'][0]['id'];self.cat.patch_movie(mid,{'notes':'Must survive backup'})
  from PIL import Image
  import io
  pic=io.BytesIO();Image.new('RGB',(120,180),'blue').save(pic,'PNG');self.cat.set_poster(mid,pic.getvalue())
  poster_before=self.cat.poster_bytes(mid)
  backup=Path(self.cat.backup());self.assertTrue(backup.is_file())
  self.cat.patch_movie(mid,{'notes':'Changed after backup'})
  (self.cat.posters/f'{mid}.jpg').unlink()
  self.cat.stage_restore(backup);self.cat.process_pending_restore();self.cat.initialize()
  self.assertEqual(self.cat.movie(mid)['notes'],'Must survive backup')
  self.assertEqual(self.cat.poster_bytes(mid),poster_before)
  self.assertTrue(list(self.cat.backups.glob('Before_Restore_*.zip')))
 def test_bad_backup_rejected(self):
  import zipfile
  bad=Path(self.tmp.name)/'danger.zip'
  with zipfile.ZipFile(bad,'w') as z:z.writestr('manifest.json','{"product":"MovieVault","schema":1}');z.writestr('movievault.sqlite','no');z.writestr('../../traversal','oops')
  with self.assertRaisesRegex(Exception,'Unexpected archive member'):self.cat.stage_restore(bad)
 def test_import_imdb_exact_match(self):
  fp=self.sample();root=self.cat.add_root(self.root);self.wait(self.cat.scan([root['id']]))
  dataset=Path(self.tmp.name)/'title.basics.tsv.gz'
  with gzip.open(dataset,'wt',encoding='utf8') as z:
   z.write('tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n')
   z.write('tt0468569\tmovie\tThe Dark Knight\tThe Dark Knight\t0\t2008\t\\N\t152\tAction,Crime,Drama\n')
   z.write('tt9999999\tmovie\tThe Dark Knight\tThe Dark Knight\t0\t2026\t\\N\t111\tThriller\n')
  self.wait(self.cat.import_imdb(dataset))
  mid=self.cat.movies()['items'][0]['id'];d=self.cat.match_imdb(mid)
  self.assertEqual(d['imdb_id'],'tt0468569');self.assertEqual(self.cat.movie(mid)['genres'],'Action,Crime,Drama')
  self.assertEqual(self.cat.settings()['auto_imdb'],'1')
 def test_manual_poster(self):
  from PIL import Image
  import io
  fp=self.sample();root=self.cat.add_root(self.root);self.wait(self.cat.scan([root['id']]))
  mid=self.cat.movies()['items'][0]['id'];buf=io.BytesIO();Image.new('RGB',(200,300),'red').save(buf,'PNG')
  self.cat.set_poster(mid,buf.getvalue())
  self.assertTrue((fp.parent/'poster.jpg').is_file())
  self.assertTrue(self.cat.poster_bytes(mid).startswith(b'\xff\xd8'))
  self.assertEqual(self.cat.movie(mid)['poster_locked'],1)
  with self.assertRaisesRegex(Exception,'supported image'):self.cat.set_poster(mid,b'not an image')
if __name__=='__main__':unittest.main(verbosity=2)

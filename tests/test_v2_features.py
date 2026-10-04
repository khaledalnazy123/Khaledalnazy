import tempfile, unittest, shutil, time, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog

class V2FeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.cat=Catalog(self.base/'db');self.root=self.base/'movies';self.root.mkdir()
        self.cat.set_settings({'auto_posters':'0','auto_imdb':'0'})
    def wait(self,jid):
        for _ in range(200):
            d=self.cat.job(jid)
            if d['state']!='running':self.assertEqual(d['state'],'completed',d['message']);return
            time.sleep(.05)
        self.fail('scan timeout')
    def fixture(self,name='Example (2021) [1080p].mkv'):
        folder=self.root/'Example';folder.mkdir(exist_ok=True)
        shutil.copyfile(Path(__file__).parent/'assets/sample.mkv',folder/name)
        (folder/'Arabic.osn.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nمرحبا',encoding='utf8')
        (folder/'English.netflix.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nHi',encoding='utf8')
        return folder
    def scan(self):
        rid=self.cat.add_root(self.root)['id'];self.wait(self.cat.scan([rid]));return self.cat.movies()['items'][0]['id']
    def test_advanced_filter_requires_same_subtitle_row(self):
        self.fixture();mid=self.scan();m=self.cat.movie(mid)
        self.assertEqual(len(m['subtitles']),2)
        self.assertEqual(next(s for s in m['subtitles'] if s['language']=='Arabic')['language'],'Arabic')
        for sub in m['subtitles']:
            self.cat.patch_subtitle(sub['id'],{'source':'OSN' if sub['language']=='Arabic' else 'Netflix'})
        self.assertEqual(self.cat.movies(subtitle_language='Arabic',subtitle_source='OSN')['total'],1)
        self.assertEqual(self.cat.movies(subtitle_language='English',subtitle_source='Netflix')['total'],1)
        self.assertEqual(self.cat.movies(subtitle_language='Arabic',subtitle_source='Netflix')['total'],0)
        self.assertEqual(self.cat.movies(genre='Action')['total'],0)
        self.cat.patch_movie(mid,{'genres':'Action, Sci-Fi','favorite':True,'personal_rating':9.0})
        self.assertEqual(self.cat.movies(genre='Action',subtitle_language='Arabic',subtitle_source='OSN',favorite='1',year_from='2020',year_to='2022')['total'],1)
        self.assertEqual(self.cat.movies(genre='Drama',subtitle_language='Arabic')['total'],0)
        self.assertEqual(self.cat.movies(year_from='2022')['total'],0)
    def test_manual_language_survives_rescan(self):
        folder=self.fixture();mid=self.scan()
        ar=next(s for s in self.cat.movie(mid)['subtitles'] if s['language']=='Arabic')
        self.cat.patch_subtitle(ar['id'],{'language':'English','translator':'Wael Mamdouh','quality':'Excellent','source':'OSN'})
        self.wait(self.cat.scan())
        row=next(s for s in self.cat.movie(mid)['subtitles'] if s['id']==ar['id'])
        self.assertEqual((row['language'],row['translator'],row['quality'],row['source'],row['language_manual']),('English','Wael Mamdouh','Excellent','OSN',1))
        # Preferred selection can be replaced without changing the original subtitle filename.
        self.cat.patch_movie(mid,{'preferred_subtitle_id':ar['id'],'playback_preference':'selected'})
        self.assertEqual(self.cat.movie(mid)['preferred_subtitle_id'],ar['id'])
        self.cat.patch_movie(mid,{'preferred_subtitle_id':None,'playback_preference':'ask'})
        self.assertIsNone(self.cat.movie(mid)['preferred_subtitle_id'])
        self.assertTrue((folder/'Arabic.osn.srt').is_file())
    def test_default_unknown_external_is_arabic(self):
        d=self.fixture();(d/'English.netflix.srt').unlink();(d/'Arabic.osn.srt').rename(d/'unknown_subtitle.srt')
        mid=self.scan();self.assertEqual(self.cat.movie(mid)['subtitles'][0]['language'],'Arabic')
    def test_custom_sources_and_theme(self):
        names=self.cat.add_subtitle_source('Islam El-Gizawy')
        self.assertIn('Islam El-Gizawy',names)
        self.cat.set_settings({'theme':'light','default_external_subtitle_lang':'English'})
        self.assertEqual(self.cat.settings()['theme'],'light')
        self.assertEqual(self.cat.settings()['default_external_subtitle_lang'],'English')
        self.cat.remove_subtitle_source('Islam El-Gizawy');self.assertNotIn('Islam El-Gizawy',self.cat.subtitle_sources())

if __name__=='__main__':unittest.main()

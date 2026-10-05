import gzip
import json
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import mv_core
from mv_core import Catalog,RAW_PROBE_MAX_BYTES,ValidationError
from mv_server import MovieServer
from tests.p2a_benchmark import BUDGETS,run_benchmark


class P2APerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.catalog=Catalog(self.base/'data')
        self.catalog.set_settings({'auto_posters':'0','poster_in_folder':'0','auto_imdb':'0'})
        self.root=self.base/'movies';self.root.mkdir();self.root_id=self.catalog.add_root(self.root)['id']

    def add_movie(self,title,group='',year=2020,resolution='1080p',subtitle=None):
        name=title+'.mkv'
        with self.catalog.connect() as db:
            movie_id=db.execute(
                '''INSERT INTO movies(root_id,relative_path,original_filename,current_filename,display_title,
                   year,release_group,resolution_tag,status,added_at,last_seen,manual_fields)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (self.root_id,name,name,name,title,year,group,resolution,'available','2026','2026','[]'),
            ).lastrowid
            if subtitle:
                db.execute(
                    '''INSERT INTO subtitles(movie_id,kind,filename,format,language,source,translator)
                       VALUES(?,?,?,?,?,?,?)''',
                    (movie_id,'external',title+'.srt','SRT',subtitle[0],subtitle[1],subtitle[2]),
                )
        return movie_id

    def test_release_group_filter_is_exact_case_insensitive_and_composable(self):
        exact=self.add_movie('Exact YTS','YTS',2020,'1080p',('Arabic','OSN','Alice'))
        self.add_movie('Other YTS Edition','yts',2021,'720p')
        self.add_movie('YTS Documentary','OTHER',2020,'1080p',('Arabic','OSN','Alice'))
        self.add_movie('YTSMX Film','YTSMX')
        self.add_movie('MYTS Film','MYTS')
        self.add_movie('YTS Other Film','YTS-OTHER')
        qxr=self.add_movie('Exact QXR','QXR')
        self.add_movie('QXR Group Film','QXR-Group')
        self.add_movie('Unlabelled','')
        unknown=self.add_movie('Literal Unknown','Unknown')

        self.assertEqual(self.catalog.movies(release_group='yTs')['total'],2)
        self.assertEqual([item['id'] for item in self.catalog.movies(release_group='qxr')['items']],[qxr])
        self.assertEqual([item['id'] for item in self.catalog.movies(release_group='UNKNOWN')['items']],[unknown])
        self.assertEqual(self.catalog.movies(release_group='')['total'],10)
        combined=self.catalog.movies(
            release_group='YTS',quality='1080p',year_from=2020,year_to=2020,
            subtitle_language='Arabic',subtitle_source='OSN',translator='Alice',
        )
        self.assertEqual([item['id'] for item in combined['items']],[exact])
        self.assertGreater(self.catalog.movies(q='YTS')['total'],self.catalog.movies(release_group='YTS')['total'])
        groups={row['group'] for row in self.catalog.groups()}
        self.assertNotIn('',groups);self.assertIn('Unknown',groups)

        server=MovieServer(self.catalog);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            query=urllib.parse.urlencode({'release_group':'YTS','quality':'1080p','year_from':2020,'year_to':2020,'subtitle_language':'Arabic'})
            request=urllib.request.Request(server.url+'api/movies?'+query,headers={'X-MovieVault-Token':server.token})
            with urllib.request.urlopen(request,timeout=5) as response:payload=json.load(response)
            self.assertEqual([item['id'] for item in payload['items']],[exact])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)
        app=(Path(__file__).resolve().parents[1]/'web'/'app.js').read_text(encoding='utf8')
        self.assertIn("args.set('release_group',state.group)",app)

    def test_scan_reuses_folder_snapshot_for_subtitles_posters_and_settings(self):
        media=self.root/'Snapshot Film (2020).mkv';media.write_bytes(b'media'*30000)
        subtitle=self.root/'Snapshot Film (2020).en.srt';subtitle.write_text('synthetic',encoding='utf8')
        from PIL import Image
        Image.new('RGB',(40,60),'navy').save(self.root/'poster.jpg')
        probe={'format':{'format_name':'matroska'},'streams':[]}
        job={'cancel':False,'total':0,'done':0,'message':''}
        with patch('mv_core.probe_media',return_value=probe),\
             patch.object(Path,'iterdir',side_effect=AssertionError('folder was listed again')),\
             patch.object(self.catalog,'settings',wraps=self.catalog.settings) as settings:
            result=self.catalog._scan_impl(job,[self.root_id])
        self.assertEqual((result['added'],result['failed_files'],result['posters_found']),(1,0,1))
        self.assertEqual(settings.call_count,1)
        movie=self.catalog.movie(self.catalog.movies()['items'][0]['id'])
        self.assertEqual([(row['filename'],row['language']) for row in movie['subtitles']],[(subtitle.name,'English')])
        self.assertEqual(movie['poster_source'],'local file')
        self.assertTrue((self.catalog.dir/movie['poster_path']).is_file())

    def test_raw_probe_snapshot_is_valid_bounded_and_keeps_useful_metadata(self):
        media=self.root/'Probe Film (2022).mkv';media.write_bytes(b'probe-media'*20000)
        streams=[
            {'index':0,'codec_type':'video','codec_name':'hevc','width':3840,'height':2160,
             'avg_frame_rate':'24000/1001','color_transfer':'smpte2084','tags':{'comment':'x'*500000}},
            {'index':1,'codec_type':'audio','codec_name':'aac','channels':6,'channel_layout':'5.1','sample_rate':'48000'},
            {'index':2,'codec_type':'subtitle','codec_name':'subrip','tags':{'language':'eng','title':'English SDH','comment':'y'*500000}},
        ]
        streams.extend({'index':i,'codec_type':'data','codec_name':'bin_data','tags':{'comment':'z'*10000}} for i in range(3,403))
        streams[3]['tags']=['malformed'];streams[3]['disposition']='malformed'
        raw={'format':{'format_name':'matroska','format_long_name':'Matroska','duration':'7200.0','bit_rate':'12000000','probe_score':float('nan'),'tags':{'comment':'q'*1000000}},'streams':streams,'irrelevant':'w'*1000000}
        with patch('mv_core.probe_media',return_value=raw):
            result=self.catalog._scan_impl({'cancel':False,'total':0,'done':0,'message':''},[self.root_id])
        self.assertEqual(result['added'],1)
        movie=self.catalog.movie(self.catalog.movies()['items'][0]['id']);encoded=movie['raw_probe'].encode('utf8')
        self.assertLessEqual(len(encoded),RAW_PROBE_MAX_BYTES)
        snapshot=json.loads(movie['raw_probe'])
        self.assertEqual(snapshot['format']['format_name'],'matroska')
        self.assertNotIn('NaN',movie['raw_probe'])
        self.assertNotIn('tags',snapshot['format']);self.assertNotIn('irrelevant',snapshot)
        self.assertTrue(snapshot['streams_truncated'])
        self.assertEqual((movie['resolution_tag'],movie['video_codec'],movie['audio_codec'],movie['hdr']),('4K','hevc','aac',1))
        embedded=[row for row in movie['subtitles'] if row['kind']=='embedded']
        self.assertEqual((embedded[0]['language'],embedded[0]['stream_index']),('English',2))

    def _write_title(self,text):
        path=self.base/'title.basics.tsv.gz'
        with gzip.open(path,'wt',encoding='utf8') as output:output.write(text)
        return path

    def _write_ratings(self,text):
        path=self.base/'title.ratings.tsv.gz'
        with gzip.open(path,'wt',encoding='utf8') as output:output.write(text)
        return path

    def _assert_title_rejected(self,path,constant,value):
        with patch.object(mv_core,constant,value):
            with self.assertRaises(ValidationError):
                self.catalog._imdb_import_impl({'cancel':False,'done':0,'total':0,'message':'','commit_completed':False},path)
        with self.catalog.connect() as db:
            rows=[tuple(row) for row in db.execute('SELECT tconst,primary_title FROM imdb_titles')]
        self.assertEqual(rows,[('tt9000000','Sentinel')]);self.assertFalse((self.catalog.dir/'imdb_stage.sqlite').exists())

    def _assert_ratings_rejected(self,path,constant,value):
        with patch.object(mv_core,constant,value):
            with self.assertRaises(ValidationError):
                self.catalog._imdb_ratings_import_impl({'cancel':False,'done':0,'total':0,'message':'','commit_completed':False},path)
        with self.catalog.connect() as db:rows=[tuple(row) for row in db.execute('SELECT * FROM imdb_ratings')]
        self.assertEqual(rows,[('tt9000000',6.5,100)]);self.assertFalse((self.catalog.dir/'imdb_ratings_stage.sqlite').exists())

    def test_title_import_bounds_compressed_decompressed_rows_lines_fields_and_stage(self):
        with self.catalog.connect() as db:db.execute('INSERT INTO imdb_titles VALUES(?,?,?,?,?,?)',('tt9000000','sentinel','Sentinel',2000,'Drama',90))
        header='tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n'
        valid='tt1234567\tmovie\tValid Movie\tValid Movie\t0\t2020\t\\N\t100\tDrama\n'
        cases=[
            ('IMDB_TITLE_MAX_COMPRESSED_BYTES',1,header+valid),
            ('IMDB_TITLE_MAX_DECOMPRESSED_BYTES',len(header.encode())+10,header+valid),
            ('IMDB_TITLE_MAX_ROWS',1,header+valid+'tt1234568\tmovie\tSecond\tSecond\t0\t2021\t\\N\t90\tDrama\n'),
            ('IMDB_TITLE_MAX_LINE_BYTES',40,header+valid),
            ('IMDB_TITLE_MAX_DECOMPRESSED_BYTES',2_000_000,header+'tt1234567\tmovie\t'+('X'*1001)+'\tX\t0\t2020\t\\N\t100\tDrama\n'),
            ('IMDB_TITLE_MAX_STAGE_BYTES',1,header+valid),
        ]
        for constant,value,text in cases:
            with self.subTest(limit=constant):self._assert_title_rejected(self._write_title(text),constant,value)

    def test_ratings_import_bounds_compressed_decompressed_rows_lines_fields_and_stage(self):
        with self.catalog.connect() as db:db.execute('INSERT INTO imdb_ratings VALUES(?,?,?)',('tt9000000',6.5,100))
        header='tconst\taverageRating\tnumVotes\n';valid='tt1234567\t8.1\t1000\n'
        cases=[
            ('IMDB_RATINGS_MAX_COMPRESSED_BYTES',1,header+valid),
            ('IMDB_RATINGS_MAX_DECOMPRESSED_BYTES',len(header.encode())+5,header+valid),
            ('IMDB_RATINGS_MAX_ROWS',1,header+valid+'tt1234568\t7.1\t900\n'),
            ('IMDB_RATINGS_MAX_LINE_BYTES',15,header+valid),
            ('IMDB_RATINGS_MAX_DECOMPRESSED_BYTES',10000,header+'tt1234567\t'+('8'*33)+'\t1000\n'),
            ('IMDB_RATINGS_MAX_STAGE_BYTES',1,header+valid),
        ]
        for constant,value,text in cases:
            with self.subTest(limit=constant):self._assert_ratings_rejected(self._write_ratings(text),constant,value)

    def _assert_benchmark(self,count):
        result=run_benchmark(count)
        for operation,limit in BUDGETS[count].items():
            self.assertLessEqual(result['measurements'][operation],limit,(operation,result))

    def test_synthetic_1000_movie_budget(self):self._assert_benchmark(1_000)
    def test_synthetic_10000_movie_budget(self):self._assert_benchmark(10_000)


if __name__=='__main__':unittest.main(verbosity=2)

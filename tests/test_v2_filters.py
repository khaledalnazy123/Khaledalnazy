from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from mv_core import Catalog,ValidationError
from mv_server import MovieServer


class FilterCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.catalog=Catalog(Path(self.temp.name)/'data')
        root=Path(self.temp.name)/'movies';root.mkdir()
        with self.catalog.connect() as db:
            root_id=db.execute('INSERT INTO roots(path) VALUES(?)',(str(root),)).lastrowid
            self.alpha=self._movie(db,root_id,'Alpha',8.5,9.0,1,'h264',5_000_000,0,'BluRay','YTS')
            self.beta=self._movie(db,root_id,'Beta',6.2,4.5,0,'HEVC',2_500_000,1,'WEB-DL','QXR')
            self.gamma=self._movie(db,root_id,'Gamma',7.4,7.0,1,'h26410',1_000_000,0,'BluRayX','YTS')
            self.unrated=self._movie(db,root_id,'Unrated',None,None,0,'av1',None,0,'DVDRip','BluRay')
            db.execute("INSERT INTO subtitles(movie_id,kind,filename,format,language,source,translator,quality) VALUES(?,?,?,?,?,?,?,?)",(self.alpha,'external','Arabic.osn.srt','SRT','Arabic','OSN','Ali','Good'))
            db.execute("INSERT INTO subtitles(movie_id,kind,filename,format,language,source,translator,quality) VALUES(?,?,?,?,?,?,?,?)",(self.alpha,'external','English.netflix.srt','SRT','English','Netflix','Bob','Excellent'))

    def _movie(self,db,root_id,title,imdb,personal,watched,codec,bitrate,estimated,source,group):
        filename=title+'.mkv'
        return db.execute('''INSERT INTO movies(root_id,relative_path,original_filename,current_filename,
            display_title,year,added_at,last_seen,imdb_rating,personal_rating,watched,video_codec,
            overall_bitrate,overall_bitrate_estimated,source,release_group,genres,cast_names)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (root_id,filename,filename,filename,title,2024,'now','now',imdb,personal,watched,codec,
             bitrate,estimated,source,group,'Drama','Actor One')).lastrowid

    def ids(self,**filters):
        return {row['id'] for row in self.catalog.movies(limit=150,**filters)['items']}

    def test_imdb_rating_min_max_range_null_and_validation(self):
        self.assertEqual(self.ids(imdb_rating_min='8'),{self.alpha})
        self.assertEqual(self.ids(imdb_rating_max='6.2'),{self.beta})
        self.assertEqual(self.ids(imdb_rating_min='7',imdb_rating_max='8'),{self.gamma})
        self.assertNotIn(self.unrated,self.ids(imdb_rating_min='0',imdb_rating_max='10'))
        for values in ({'imdb_rating_min':'-0.1'},{'imdb_rating_max':'10.1'},{'imdb_rating_min':'8','imdb_rating_max':'7'},{'imdb_rating_min':'bad'}):
            with self.subTest(values=values),self.assertRaises(ValidationError):self.catalog.movies(**values)

    def test_personal_rating_min_max_range_null_and_validation(self):
        self.assertEqual(self.ids(personal_rating_min='8'),{self.alpha})
        self.assertEqual(self.ids(personal_rating_max='4.5'),{self.beta})
        self.assertEqual(self.ids(personal_rating_min='6',personal_rating_max='8'),{self.gamma})
        self.assertNotIn(self.unrated,self.ids(personal_rating_min='0',personal_rating_max='10'))
        with self.assertRaises(ValidationError):self.catalog.movies(personal_rating_min='9',personal_rating_max='2')

    def test_watched_and_unwatched(self):
        self.assertEqual(self.ids(watched='1'),{self.alpha,self.gamma})
        self.assertEqual(self.ids(watched='0'),{self.beta,self.unrated})

    def test_video_codec_is_case_insensitive_and_exact(self):
        self.assertEqual(self.ids(video_codec='H264'),{self.alpha})
        self.assertEqual(self.ids(video_codec='hevc'),{self.beta})
        self.assertEqual(self.ids(video_codec='vp9'),set())

    def test_overall_bitrate_kbps_min_max_range_null_invalid_and_estimated(self):
        self.assertEqual(self.ids(overall_bitrate_min_kbps='3000'),{self.alpha})
        self.assertEqual(self.ids(overall_bitrate_max_kbps='1000'),{self.gamma})
        self.assertEqual(self.ids(overall_bitrate_min_kbps='2000',overall_bitrate_max_kbps='3000'),{self.beta})
        self.assertIn(self.beta,self.ids(overall_bitrate_min_kbps='2500',overall_bitrate_max_kbps='2500'))
        self.assertNotIn(self.unrated,self.ids(overall_bitrate_min_kbps='0'))
        for values in ({'overall_bitrate_min_kbps':'-1'},{'overall_bitrate_max_kbps':'nope'},{'overall_bitrate_min_kbps':'3000','overall_bitrate_max_kbps':'2000'}):
            with self.subTest(values=values),self.assertRaises(ValidationError):self.catalog.movies(**values)

    def test_movie_source_is_case_insensitive_exact_and_not_release_group(self):
        self.assertEqual(self.ids(source='bluray'),{self.alpha})
        self.assertEqual(self.ids(source='web-dl'),{self.beta})
        self.assertNotIn(self.unrated,self.ids(source='BluRay'))
        self.assertEqual(self.ids(source='QXR'),set())

    def test_subtitle_quality_uses_same_correlated_subtitle_row(self):
        self.assertEqual(self.ids(subtitle_quality='good'),{self.alpha})
        self.assertEqual(self.ids(subtitle_language='Arabic',subtitle_source='osn',translator='Ali',subtitle_quality='GOOD'),{self.alpha})
        self.assertEqual(self.ids(subtitle_language='Arabic',subtitle_source='Netflix',translator='Bob',subtitle_quality='Excellent'),set())

    def test_multiple_movie_filters_compose_and_api_passes_every_new_parameter(self):
        filters={'imdb_rating_min':'8','imdb_rating_max':'9','personal_rating_min':'8','personal_rating_max':'10',
                 'watched':'1','video_codec':'H264','overall_bitrate_min_kbps':'4000',
                 'overall_bitrate_max_kbps':'6000','source':'bluray','subtitle_language':'Arabic',
                 'subtitle_source':'OSN','translator':'Ali','subtitle_quality':'Good'}
        self.assertEqual(self.ids(**filters),{self.alpha})
        server=MovieServer(self.catalog);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            request=urllib.request.Request(server.url+'api/movies?'+urllib.parse.urlencode(filters),headers={'X-MovieVault-Token':server.token})
            with urllib.request.urlopen(request,timeout=5) as response:
                payload=json.load(response)
            self.assertEqual([row['id'] for row in payload['items']],[self.alpha])
            invalid=urllib.request.Request(server.url+'api/movies?overall_bitrate_min_kbps=-1',headers={'X-MovieVault-Token':server.token})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(invalid,timeout=5)
            self.assertEqual(caught.exception.code,400)
            with caught.exception as response:self.assertIn('Invalid overall bitrate minimum',json.load(response)['error'])
        finally:
            server.shutdown();server.server_close();thread.join(2)

    def test_ui_query_mapping_and_clear_cover_all_new_controls(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf8')
        js=(ROOT/'web/app.js').read_text(encoding='utf8')
        expected={'imdb_rating_min':'fImdbRatingMin','imdb_rating_max':'fImdbRatingMax',
                  'personal_rating_min':'fPersonalRatingMin','personal_rating_max':'fPersonalRatingMax',
                  'watched':'fWatched','video_codec':'fVideoCodec',
                  'overall_bitrate_min_kbps':'fBitrateMin','overall_bitrate_max_kbps':'fBitrateMax',
                  'source':'fMovieSource','subtitle_quality':'fSubtitleQuality'}
        mapping=re.search(r'ADVANCED_FILTER_FIELDS=Object\.freeze\(\{([^}]*)\}\)',js)
        self.assertIsNotNone(mapping)
        for parameter,control in expected.items():
            self.assertIn(f'id="{control}"',html)
            self.assertIn(f"{parameter}:'{control}'",mapping.group(1))
        self.assertIn('Object.entries(ADVANCED_FILTER_FIELDS)',js)
        self.assertIn("for(const id of Object.values(ADVANCED_FILTER_FIELDS))$(id).value=''",js)


if __name__=='__main__':unittest.main(verbosity=2)

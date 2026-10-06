"""Protect the UI wiring: each persistent JS event binding must have a real HTML element.

Dynamic modal controls are covered by visual_smoke.py.
"""
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class V2UIContract(unittest.TestCase):
    def test_persistent_controls_exist(self):
        html = (ROOT/'web/index.html').read_text(encoding='utf8')
        names = set(re.findall(r'\bid="([A-Za-z][A-Za-z0-9]*)"', html))
        self.assertEqual(len(names), len(re.findall(r'\bid="[A-Za-z][A-Za-z0-9]*"', html)), 'Duplicate HTML IDs')
        required = {
            'updateAllBtn','cancelActiveJob','migrationBanner','openMigration','migrationPanel',
            'legacyChoose','legacyChooseZip','legacyDetect','legacyPreview','legacyImport',
            'legacyPath','legacySummary','connectGemini','geminiKey','geminiModel',
            'geminiState','disconnectGemini','diagnosticExport','downloadImdbRatings',
            'defaultSubLang','themeChoice','addSubtitleSource','newSubtitleSource',
            'fGenre','fActor','fSubtitleLanguage','fSubtitleSource','fTranslator',
            'fYearFrom','fYearTo','fFavorite','fImdbRatingMin','fImdbRatingMax',
            'fPersonalRatingMin','fPersonalRatingMax','fWatched','fVideoCodec',
            'fBitrateMin','fBitrateMax','fMovieSource','fSubtitleQuality','clearAdvancedFilters',
        }
        self.assertFalse(required-names, f'Missing HTML controls: {required-names}')
    def test_scope_lock_filters_are_serialized_and_cleared_from_one_mapping(self):
        js=(ROOT/'web/app.js').read_text(encoding='utf8')
        expected={
            'imdb_rating_min':'fImdbRatingMin','imdb_rating_max':'fImdbRatingMax',
            'personal_rating_min':'fPersonalRatingMin','personal_rating_max':'fPersonalRatingMax',
            'watched':'fWatched','video_codec':'fVideoCodec',
            'overall_bitrate_min_kbps':'fBitrateMin','overall_bitrate_max_kbps':'fBitrateMax',
            'source':'fMovieSource','subtitle_quality':'fSubtitleQuality',
        }
        mapping=re.search(r'ADVANCED_FILTER_FIELDS=Object\.freeze\(\{([^}]*)\}\)',js)
        self.assertIsNotNone(mapping)
        for parameter,control in expected.items():
            self.assertIn(f"{parameter}:'{control}'",mapping.group(1))
        self.assertIn('Object.entries(ADVANCED_FILTER_FIELDS)',js)
        self.assertIn('for(const id of Object.values(ADVANCED_FILTER_FIELDS))$(id).value=\'\'',js)
    def test_native_webview_is_never_publicly_exposed(self):
        server=(ROOT/'mv_server.py').read_text(encoding='utf8')
        self.assertIn('self._window = None', server)
        self.assertNotRegex(server, r'self\.window\s*=')
    def test_v2_installs_next_to_v1(self):
        s=(ROOT/'MovieVault.iss').read_text(encoding='utf8')
        self.assertIn('Programs\\MovieVaultV2',s)
        self.assertNotIn('OutputBaseFilename=MovieVault_Setup_v1',s)

if __name__=='__main__': unittest.main()

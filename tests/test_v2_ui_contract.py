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
            'fYearFrom','fYearTo','fFavorite','clearAdvancedFilters',
        }
        self.assertFalse(required-names, f'Missing HTML controls: {required-names}')
    def test_native_webview_is_never_publicly_exposed(self):
        server=(ROOT/'mv_server.py').read_text(encoding='utf8')
        self.assertIn('self._window = None', server)
        self.assertNotRegex(server, r'self\.window\s*=')
    def test_v2_installs_next_to_v1(self):
        s=(ROOT/'MovieVault.iss').read_text(encoding='utf8')
        self.assertIn('Programs\\MovieVaultV2',s)
        self.assertNotIn('OutputBaseFilename=MovieVault_Setup_v1',s)

if __name__=='__main__': unittest.main()

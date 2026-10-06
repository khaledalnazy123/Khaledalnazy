"""P2C security, privacy, artifact, and real-live-server browser regressions."""
from __future__ import annotations

import http.client
import json
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mv_core import Catalog,ValidationError
from mv_diagnostics import _safe
from mv_server import MovieServer

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # The core suite remains runnable without the optional QA browser.
    sync_playwright=None


class LiveServerCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.catalog=Catalog(self.base/'data');self.catalog.set_settings({'auto_posters':'0'})
        self.server=MovieServer(self.catalog)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def raw(self,path='/',host=None,token=None,duplicate_host=None,method='GET',body=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.putrequest(method,path,skip_host=True,skip_accept_encoding=True)
        if host is not None:conn.putheader('Host',host)
        if duplicate_host is not None:conn.putheader('Host',duplicate_host)
        if token is not None:conn.putheader('X-MovieVault-Token',token)
        if body is not None:
            encoded=json.dumps(body).encode();conn.putheader('Content-Type','application/json');conn.putheader('Content-Length',str(len(encoded)))
        else:encoded=None
        conn.endheaders(encoded)
        response=conn.getresponse();data=response.read();headers=dict(response.getheaders());status=response.status
        conn.close();return status,data,headers

    def expected_host(self,name='127.0.0.1'):
        return f'{name}:{self.server.server_port}'


class HostAndHttpSecurityTests(LiveServerCase):
    def test_ipv4_exact_host_serves_token_bootstrap(self):
        status,body,_=self.raw(host=self.expected_host())
        self.assertEqual(status,200);self.assertIn(self.server.token.encode(),body)

    def test_localhost_hostname_is_case_normalized(self):
        status,_,_=self.raw(host=self.expected_host('LOCALHOST'))
        self.assertEqual(status,200)

    def test_malicious_host_cannot_receive_root_token(self):
        status,body,_=self.raw(host=f'attacker.example:{self.server.server_port}')
        self.assertEqual(status,400);self.assertNotIn(self.server.token.encode(),body)

    def test_missing_port_host_is_rejected(self):
        status,body,_=self.raw(host='localhost')
        self.assertEqual(status,400);self.assertNotIn(self.server.token.encode(),body)

    def test_duplicate_host_is_rejected(self):
        status,body,_=self.raw(host=self.expected_host(),duplicate_host=f'evil.example:{self.server.server_port}')
        self.assertEqual(status,400);self.assertNotIn(self.server.token.encode(),body)

    def test_invalid_host_precedes_static_favicon_and_not_found_dispatch(self):
        for path in ('/style.css','/app.js','/favicon.ico','/not-found'):
            with self.subTest(path=path):self.assertEqual(self.raw(path,host='evil.invalid')[0],400)

    def test_artwork_requires_both_valid_host_and_session_token(self):
        valid=self.expected_host()
        self.assertEqual(self.raw('/artwork/999?k=wrong',host=valid)[0],400)
        self.assertEqual(self.raw(f'/artwork/999?k={self.server.token}',host='evil.invalid')[0],400)
        self.assertEqual(self.raw(f'/artwork/999?k={self.server.token}',host=valid)[0],404)

    def test_api_still_requires_session_token(self):
        self.assertEqual(self.raw('/api/bootstrap',host=self.expected_host())[0],400)
        self.assertEqual(self.raw('/api/bootstrap',host=self.expected_host(),token=self.server.token)[0],200)

    def test_security_headers_and_strict_csp_apply_to_html_static_and_errors(self):
        for path in ('/','/style.css','/not-found'):
            status,_,headers=self.raw(path,host=self.expected_host(),token=self.server.token)
            with self.subTest(path=path,status=status):
                csp=headers['Content-Security-Policy']
                self.assertNotIn("'unsafe-inline'",csp);self.assertNotIn("'unsafe-eval'",csp)
                self.assertIn("script-src 'self'",csp);self.assertIn("style-src 'self'",csp)
                self.assertIn("frame-ancestors 'none'",csp);self.assertIn("base-uri 'none'",csp)
                self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
                self.assertEqual(headers['Referrer-Policy'],'no-referrer')
                self.assertEqual(headers['X-Frame-Options'],'DENY')
                self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertNotIn('Strict-Transport-Security',headers)

    def test_expected_validation_message_is_safe(self):
        status,body,_=self.raw('/api/movies?year_from=invalid',host=self.expected_host(),token=self.server.token)
        self.assertEqual(status,400);self.assertIn(b'Invalid production year filter',body)

    def test_unexpected_exception_is_generic_and_failure_class_is_diagnostic(self):
        secret=r'C:\Users\Alice\Private Movie.mkv'
        with patch.object(self.catalog,'stats',side_effect=RuntimeError(secret)):
            status,body,_=self.raw('/api/bootstrap',host=self.expected_host(),token=self.server.token)
        self.assertEqual(status,500);self.assertEqual(json.loads(body),{'error':'Internal server error'})
        log=self.catalog.diagnostics.path.read_text(encoding='utf8')
        self.assertIn('http_request_failed',log);self.assertIn('RuntimeError',log);self.assertNotIn('Alice',log)


class CspStaticAuditTests(unittest.TestCase):
    def setUp(self):
        self.html=(ROOT/'web/index.html').read_text(encoding='utf8')
        self.js=(ROOT/'web/app.js').read_text(encoding='utf8')
        self.server=(ROOT/'mv_server.py').read_text(encoding='utf8')

    def test_html_has_no_inline_styles_scripts_or_event_handlers(self):
        self.assertNotRegex(self.html,r'\sstyle\s*=')
        self.assertNotRegex(self.html,r'\son[a-z]+\s*=')
        self.assertEqual(re.findall(r'<script[^>]*>(.*?)</script>',self.html,re.S),[''])

    def test_generated_ui_has_no_style_attributes_or_inline_handlers(self):
        self.assertNotRegex(self.js,r'style\s*=')
        self.assertNotRegex(self.js,r'\son(?:error|load|click)\s*=')
        self.assertNotIn('.style.',self.js)

    def test_server_csp_has_no_inline_or_eval_escape_hatches(self):
        csp=re.search(r"Content-Security-Policy',([^\n]+)",self.server).group(1)
        self.assertNotIn('unsafe-inline',csp);self.assertNotIn('unsafe-eval',csp)
        self.assertIn("script-src 'self'",csp);self.assertIn("style-src 'self'",csp)


class DiagnosticPrivacyTests(LiveServerCase):
    def test_jwt_shaped_secret_is_redacted(self):
        value='eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz012345'
        self.assertEqual(_safe(value),'[REDACTED JWT]')

    def test_windows_backslash_path_is_redacted(self):
        self.assertNotIn('Alice',_safe(r'Opened C:\Users\Alice Name\Movies\Private Film.mkv'))

    def test_windows_forward_slash_path_is_redacted(self):
        self.assertNotIn('Private Film',_safe('Opened D:/Media/Private Film (2025).mkv'))

    def test_unc_path_is_redacted(self):
        self.assertNotIn('server',_safe(r'\\server\private share\Film Name.mkv'))

    def test_linux_and_macos_paths_are_redacted(self):
        for value in ('/home/alice/Movies/Film.mkv','/Users/alice/Movies/Film.mkv','/Volumes/Private/Film.mkv','/var/lib/movievault/Film.mkv','/Applications/MovieVault/Film.mkv'):
            with self.subTest(value=value):self.assertNotIn('alice',_safe(value));self.assertNotIn('Film',_safe(value))

    def test_email_like_credential_is_redacted(self):
        self.assertNotIn('alice.private@example.com',_safe('login alice.private@example.com'))

    def test_standalone_movie_and_subtitle_filenames_are_redacted(self):
        for value in ('Secret Film 2026.mkv','Private Subtitle Name.ass','Episode 01.srt'):
            with self.subTest(value=value):self.assertNotIn(Path(value).stem,_safe('file '+value))

    def test_adversarial_export_contains_no_sensitive_samples_and_keeps_safe_fields(self):
        samples=[
            r'C:\Users\Alice Name\Movies\Private Film.mkv',r'D:/Private/Forward Slash Film.mp4',
            r'\\nas-box\Secret Share\Hidden Title.mkv','/Users/alice/Movies/Mac Secret.mov',
            '/home/alice/Movies/Linux Secret.mkv','private.user@example.com',
            'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz012345',
            'Standalone Private Subtitle.srt',
        ]
        for sample in samples:self.catalog.diagnostics.event('scan_file_skipped',root_id=7,failure_type='OSError',message=sample)
        archive=Path(self.catalog.diagnostics.export(self.catalog))
        with zipfile.ZipFile(archive) as z:raw='\n'.join(z.read(name).decode('utf8') for name in z.namelist())
        for leak in ('Alice Name','Forward Slash Film','Secret Share','Mac Secret','Linux Secret','private.user@example.com','eyJhbGciOiJIUzI1NiJ9','Standalone Private Subtitle'):
            self.assertNotIn(leak,raw)
        self.assertIn('scan_file_skipped',raw);self.assertIn('OSError',raw);self.assertIn('catalog_counts',raw)


class BackupAndArtifactTests(unittest.TestCase):
    def test_backup_ui_discloses_sensitive_unencrypted_contents_and_exclusions(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf8')
        for phrase in ('filenames','watched-folder paths','notes','no video files','no TMDb or Gemini credentials','not encrypted or anonymized','sensitive personal data'):
            self.assertIn(phrase,html)

    def test_backup_confirm_post_creation_and_restore_wording_are_explicit(self):
        js=(ROOT/'web/app.js').read_text(encoding='utf8');html=(ROOT/'web/index.html').read_text(encoding='utf8')
        self.assertIn('Create an unencrypted full backup',js)
        self.assertIn('Sensitive, unencrypted backup saved',js)
        self.assertIn('full, non-anonymized backup',js)
        self.assertIn('full, non-anonymized backup contents',html)

    def test_visual_outputs_are_ignored_and_never_target_tracked_docs(self):
        smoke=(ROOT/'tests/visual_smoke.py').read_text(encoding='utf8')
        ignore=(ROOT/'.gitignore').read_text(encoding='utf8')
        self.assertIn("HERE/'qa_reports'/'visual'",smoke);self.assertIn('/qa_reports/',ignore)
        self.assertNotIn("HERE/'docs/",smoke)
        for name in ('V2_Home_UI_Test.png','V2_Movie_Details_UI_Test.png','V2_Settings_UI_Test.png','TEST_OUTPUT.txt','VISUAL_TEST_OUTPUT.txt'):
            self.assertFalse((ROOT/'docs'/name).exists())


@unittest.skipUnless(sync_playwright,'Playwright is required for live browser E2E')
class RealMovieServerBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name)
        cls.catalog=Catalog(cls.base/'data');cls.catalog.set_settings({'auto_posters':'0'})
        movies=cls.base/'movies';movies.mkdir();folder=movies/'Live E2E Movie';folder.mkdir()
        shutil.copyfile(ROOT/'tests/assets/sample.mkv',folder/'Live E2E Movie (2024) [1080p] [YTS].mkv')
        root=cls.catalog.add_root(movies);job=cls.catalog.scan([root['id']])
        for _ in range(300):
            if cls.catalog.job(job)['state']!='running':break
            time.sleep(.02)
        if cls.catalog.job(job)['state']!='completed':raise RuntimeError(cls.catalog.job(job))
        cls.server=MovieServer(cls.catalog);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.playwright=sync_playwright().start()
        launch={'headless':True,'args':['--no-sandbox']}
        if Path('/usr/bin/chromium').exists():launch['executable_path']='/usr/bin/chromium'
        cls.browser=cls.playwright.chromium.launch(**launch)
        cls.page=cls.browser.new_page(viewport={'width':1440,'height':900})
        cls.console_errors=[];cls.page_errors=[]
        cls.page.on('console',lambda msg:cls.console_errors.append(msg.text) if msg.type=='error' else None)
        cls.page.on('pageerror',lambda error:cls.page_errors.append(str(error)))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.playwright.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join(2);cls.temp.cleanup()

    def test_01_real_transport_happy_path_navigation_and_data(self):
        response=self.page.goto(self.server.url,wait_until='networkidle')
        self.assertEqual(response.status,200);self.assertNotIn('unsafe-inline',response.headers['content-security-policy'])
        self.assertEqual(self.page.locator('.movie-card').count(),1)
        self.page.locator('.movie-card').click();self.page.wait_for_selector('#modalContent .detail-title')
        self.assertIn('Live E2E Movie',self.page.locator('#modalContent').inner_text())
        self.page.locator('#closeModal').click();self.page.locator('.nav[data-view=settings]').click()
        self.assertTrue(self.page.locator('#settingsView').is_visible())
        self.assertIn('not encrypted or anonymized',self.page.locator('#settingsView').inner_text())
        self.assertEqual(self.page_errors,[]);self.assertEqual(self.console_errors,[])

    def test_02_controlled_failures_are_safe_and_ui_recovers(self):
        token=self.server.token
        results=self.page.evaluate("""async token=>{
          const call=async(url,options={})=>{const r=await fetch(url,options);return [r.status,await r.text()]};
          return {
            static_asset:await call('/style.css'),
            unauthorized:await call('/api/bootstrap'),
            invalid:await call('/api/movies?year_from=nope',{headers:{'X-MovieVault-Token':token}}),
            missing:await call('/api/movies/999999',{headers:{'X-MovieVault-Token':token}}),
            artwork:await call('/artwork/999?k=bad')
          };
        }""",token)
        self.assertEqual(results['static_asset'][0],200);self.assertEqual(results['unauthorized'][0],400);self.assertEqual(results['invalid'][0],400)
        self.assertEqual(results['missing'][0],400);self.assertEqual(results['artwork'][0],400)
        invalid_host=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        invalid_host.putrequest('GET','/',skip_host=True);invalid_host.putheader('Host','attacker.invalid');invalid_host.endheaders()
        rejected=invalid_host.getresponse();rejected_body=rejected.read();invalid_host.close()
        self.assertEqual(rejected.status,400);self.assertNotIn(token.encode(),rejected_body)
        with self.catalog._exclusive_maintenance('e2e_test','busy'):
            busy=self.page.evaluate("""async token=>{const r=await fetch('/api/scan',{method:'POST',headers:{'X-MovieVault-Token':token,'Content-Type':'application/json'},body:'{}'});return [r.status,await r.text()]}""",token)
        self.assertEqual(busy[0],409)
        original=self.catalog.fetch_missing_posters
        self.catalog.fetch_missing_posters=lambda limit=10:(_ for _ in ()).throw(ValidationError('Provider unavailable; retry later'))
        try:
            self.page.locator('#findMorePosters').click();self.page.wait_for_timeout(150)
            self.assertIn('Provider unavailable',self.page.locator('#toast').inner_text())
            self.assertTrue(self.page.locator('#settingsView').is_visible())
        finally:self.catalog.fetch_missing_posters=original
        self.assertEqual(self.page_errors,[])
        self.assertFalse([message for message in self.console_errors if 'content security' in message.lower() or 'refused to' in message.lower()])
        # Chromium reports deliberate 400/409 fetch probes as resource errors;
        # they are expected transport outcomes, not application/CSP failures.
        self.console_errors.clear()

    def test_03_no_page_console_or_csp_errors(self):
        self.assertEqual(self.page_errors,[]);self.assertEqual(self.console_errors,[])


if __name__=='__main__':unittest.main(verbosity=2)

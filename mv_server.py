"""Loopback-only, token-protected HTTP transport for MovieVault native WebView."""
from __future__ import annotations
import json,mimetypes,os,re,secrets,subprocess,sys,threading,urllib.parse,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from mv_core import Catalog,BusyError,ValidationError,VERSION,default_data_dir
from mv_playback import playback_plan,launch_playback,PlaybackError,SubtitleChoiceRequired
from mv_migration import legacy_data_dir,resolve_legacy_source,stage_migration,apply_pending_migration,MigrationError

WEB=Path(__file__).parent/'web'
if getattr(sys,'frozen',False):WEB=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'web'
MAX_BODY=13_000_000

def launch_path(path):
    if not Path(path).exists():raise ValidationError('File or folder not currently available')
    if sys.platform=='win32':os.startfile(str(path))
    elif sys.platform=='darwin':subprocess.Popen(['open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:subprocess.Popen(['xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

class MovieServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,catalog:Catalog,port=0):
        self.catalog=catalog;self.token=secrets.token_urlsafe(36)
        super().__init__(('127.0.0.1',port),Request)
    @property
    def url(self):return f'http://127.0.0.1:{self.server_port}/'

class Request(BaseHTTPRequestHandler):
    server:MovieServer
    def log_message(self,fmt,*args):pass
    def _headers(self,ctype,code=200,size=None):
        self.send_response(code)
        self.send_header('Content-Type',ctype)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob: https://www.themoviedb.org; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if size is not None:self.send_header('Content-Length',str(size))
        self.end_headers()
        # Activity records do not contain query parameters or request bodies.
        route=urllib.parse.urlsplit(self.path).path
        if route.startswith('/api/') and not route.startswith('/api/jobs/') and route not in ('/api/bootstrap','/api/diagnostics/status'):
            self.server.catalog.diagnostics.event('api_request',method=self.command,route=route,status=code)
    def _json(self,d,code=200):
        raw=json.dumps(d,ensure_ascii=False,default=str).encode('utf-8');self._headers('application/json; charset=utf-8',code,len(raw));self.wfile.write(raw)
    def _bytes(self,b,mime):self._headers(mime,200,len(b));self.wfile.write(b)
    def _auth(self):
        if self.headers.get('Host','') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):raise ValidationError('Invalid host')
        if self.headers.get('X-MovieVault-Token')!=self.server.token:raise ValidationError('Unauthorized client')
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            raise ValidationError('Invalid origin')
    def _body(self):
        try:size=int(self.headers.get('Content-Length',0))
        except ValueError:raise ValidationError('Invalid content length')
        if not 0<size<=MAX_BODY:raise ValidationError('Request is empty or exceeds 13 MB limit')
        raw=self.rfile.read(size)
        if len(raw)!=size:raise ValidationError('Incomplete request')
        if self.headers.get('Content-Type','').startswith('application/json'):
            d=json.loads(raw)
            if not isinstance(d,dict):raise ValidationError('JSON object required')
            return d
        return raw
    def do_GET(self):
        try:
            parsed=urllib.parse.urlsplit(self.path);path=parsed.path
            if path=='/':
                template=(WEB/'index.html').read_text(encoding='utf8')
                html=template.replace('{{APP_TOKEN}}',self.server.token).replace('{{APP_VERSION}}',VERSION)
                return self._bytes(html.encode('utf8'),'text/html; charset=utf-8')
            if path in ('/style.css','/app.js'):
                f=WEB/path[1:];return self._bytes(f.read_bytes(),mimetypes.guess_type(str(f))[0] or 'text/plain')
            if path=='/favicon.ico':return self._headers('image/x-icon',204)
            query=urllib.parse.parse_qs(parsed.query)
            # <img> elements cannot set custom authorization headers. Scope artwork URLs to this ephemeral session key.
            art=re.fullmatch(r'/artwork/(\d+)',path)
            if art:
                if query.get('k',[''])[0]!=self.server.token:raise ValidationError('Unauthorized artwork access')
                data=self.server.catalog.poster_bytes(int(art[1]))
                if data:return self._bytes(data,'image/jpeg')
                return self._headers('image/jpeg',404)
            self._auth();cat=self.server.catalog
            def arg(k,default=''):return query.get(k,[default])[0]
            if path=='/api/migration/detect':
                try:return self._json(resolve_legacy_source())
                except MigrationError as e:return self._json({'found':False,'hint':str(e),'suggested_path':str(legacy_data_dir())})
            if path=='/api/bootstrap':return self._json({'version':VERSION,'stats':cat.stats(),'roots':cat.roots(),'settings':cat.settings(),'tmdb':cat.tmdb_status(),'gemini':cat.gemini_status(),'data_dir':str(cat.dir),'active_job':cat.job(cat.active_job) if cat.active_job else None})
            if path=='/api/movies':return self._json(cat.movies(q=arg('q'),status=arg('status'),quality=arg('quality'),sort=arg('sort','recent'),page=int(arg('page','1')),limit=int(arg('limit','54')),genre=arg('genre'),actor=arg('actor'),subtitle_language=arg('subtitle_language'),subtitle_source=arg('subtitle_source'),translator=arg('translator'),year_from=arg('year_from'),year_to=arg('year_to'),favorite=arg('favorite'),watched=arg('watched')))
            if path=='/api/groups':return self._json({'items':cat.groups()})
            if path=='/api/subtitle-sources':return self._json({'items':cat.subtitle_sources()})
            if path=='/api/diagnostics/status':return self._json({'logging':True,'path':str(cat.diagnostics.folder),'credentials_included':False})
            if path=='/api/tmdb/status':return self._json(cat.tmdb_status())
            m=re.fullmatch(r'/api/movies/(\d+)',path)
            if m:
                d=cat.movie(int(m[1]));return self._json(d)
            m=re.fullmatch(r'/api/jobs/(\d+)',path)
            if m:return self._json(cat.job(m[1]))
            m=re.fullmatch(r'/artwork/(\d+)',path)
            if m:
                data=cat.poster_bytes(int(m[1]))
                if data:return self._bytes(data,'image/jpeg')
                return self._headers('image/jpeg',404)
            self._json({'error':'Not found'},404)
        except (ValidationError,MigrationError,ValueError,KeyError) as e:self._json({'error':str(e)},400)
        except Exception as e:self._json({'error':'Internal error: '+str(e)[:120]},500)
    def do_POST(self):
        try:
            self._auth();path=urllib.parse.urlsplit(self.path).path;cat=self.server.catalog
            b=self._body()
            if path=='/api/roots':return self._json(cat.add_root(b.get('path','')))
            if path=='/api/update-all':return self._json({'job_id':cat.smart_update(b.get('mode','quick'),b.get('include_gemini',False),b.get('limit',100))},202)
            m=re.fullmatch(r'/api/jobs/(\d+)/cancel',path)
            if m:return self._json(cat.cancel_job(m[1]))
            if path=='/api/scan':
                ids=b.get('root_ids')
                if ids is not None and (not isinstance(ids,list) or not all(isinstance(x,int) for x in ids)):raise ValidationError('Invalid root ID list')
                return self._json({'job_id':cat.scan(ids)},202)
            if path=='/api/settings':return self._json(cat.set_settings(b))
            if path=='/api/subtitle-sources':return self._json({'items':cat.add_subtitle_source(b.get('name'))})
            if path=='/api/diagnostics/export':return self._json({'path':cat.diagnostics.export(cat)})
            if path=='/api/tmdb/connect':return self._json(cat.connect_tmdb(b.get('read_token','')))
            if path=='/api/tmdb/disconnect':return self._json(cat.disconnect_tmdb())
            if path=='/api/gemini/connect':return self._json(cat.connect_gemini(b.get('api_key','')))
            if path=='/api/gemini/disconnect':return self._json(cat.disconnect_gemini())
            if path=='/api/imdb/import':return self._json({'job_id':cat.import_imdb(b.get('path',''))},202)
            if path=='/api/imdb/download':return self._json({'job_id':cat.download_imdb()},202)
            if path=='/api/imdb/ratings/download':return self._json({'job_id':cat.download_imdb_ratings()},202)
            if path=='/api/imdb/ratings/import':return self._json({'job_id':cat.import_imdb_ratings(b.get('path',''))},202)
            if path=='/api/posters/batch':return self._json({'job_id':cat.fetch_missing_posters(b.get('limit',10))},202)
            if path=='/api/backup':return self._json({'path':cat.backup(b.get('path'))})
            if path=='/api/migration/preview':return self._json(resolve_legacy_source(b.get('path')))
            if path=='/api/migration/stage':return self._json(stage_migration(b.get('path'),cat.dir))
            if path=='/api/restore':return self._json({'message':cat.stage_restore(b.get('path',''))})
            m=re.fullmatch(r'/api/movies/(\d+)/ai/resolve',path)
            if m:return self._json({'job_id':cat.resolve_ai(int(m[1]))},202)
            m=re.fullmatch(r'/api/movies/(\d+)/details/refresh',path)
            if m:return self._json({'job_id':cat.refresh_movie_details(int(m[1]))},202)
            m=re.fullmatch(r'/api/movies/(\d+)/match',path)
            if m:return self._json(cat.match_imdb(int(m[1])))
            m=re.fullmatch(r'/api/movies/(\d+)/poster/fetch',path)
            if m:return self._json({'job_id':cat.fetch_poster(int(m[1]),replace=bool(b.get('replace',False)))},202)
            m=re.fullmatch(r'/api/movies/(\d+)/poster/generate',path)
            if m:return self._json({'job_id':cat.generate_frame_poster(int(m[1]))},202)
            m=re.fullmatch(r'/api/movies/(\d+)/poster/upload',path)
            if m:
                if isinstance(b,dict):raise ValidationError('Expected binary image')
                cat.set_poster(int(m[1]),b)
                return self._json({'ok':True})
            m=re.fullmatch(r'/api/movies/(\d+)/(play|folder)',path)
            if m:
                d=cat.movie(int(m[1]));base=Path(d['path'])
                if d['status']!='available' or not base.is_file():raise ValidationError('Movie is not available on disk')
                if m[2]=='folder':
                    launch_path(base.parent)
                    return self._json({'ok':True})
                try:
                    plan=playback_plan(d,subtitle_id=b.get('subtitle_id'),no_subtitles=bool(b.get('no_subtitles',False)))
                    return self._json({'ok':True,**launch_playback(plan,native_launch=launch_path)})
                except SubtitleChoiceRequired:
                    return self._json({'error':'Choose a subtitle for this movie.','needs_selection':True,'subtitles':[{'id':s['id'],'language':s['language'],'source':s['source'],'filename':s['filename'],'kind':s['kind']} for s in d['subtitles']]},409)
            self._json({'error':'Unknown route'},404)
        except BusyError as e:self._json({'error':str(e)},409)
        except (ValidationError,MigrationError,PlaybackError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self._json({'error':str(e)},400)
        except Exception as e:self._json({'error':'Internal error: '+str(e)[:120]},500)
    def do_PATCH(self):
        try:
            self._auth();path=urllib.parse.urlsplit(self.path).path;cat=self.server.catalog;b=self._body()
            m=re.fullmatch(r'/api/movies/(\d+)',path)
            if m:return self._json(cat.patch_movie(int(m[1]),b))
            m=re.fullmatch(r'/api/subtitles/(\d+)',path)
            if m:
                cat.patch_subtitle(int(m[1]),b);return self._json({'ok':True})
            self._json({'error':'Unknown route'},404)
        except (ValidationError,MigrationError,ValueError,KeyError) as e:self._json({'error':str(e)},400)
        except Exception as e:self._json({'error':'Internal error: '+str(e)[:120]},500)
    def do_DELETE(self):
        try:
            self._auth();parsed=urllib.parse.urlsplit(self.path);m=re.fullmatch(r'/api/roots/(\d+)',parsed.path)
            if parsed.path=='/api/subtitle-sources':
                name=urllib.parse.parse_qs(parsed.query).get('name',[''])[0]
                return self._json({'items':self.server.catalog.remove_subtitle_source(name)})
            if m:self.server.catalog.disable_root(int(m[1]));return self._json({'ok':True})
            self._json({'error':'Unknown route'},404)
        except (ValidationError,ValueError) as e:self._json({'error':str(e)},400)
        except Exception as e:self._json({'error':'Internal error: '+str(e)[:120]},500)

class DesktopApi:
    def __init__(self):
        # IMPORTANT: do not expose the native Window as a public js_api attribute.
        # pywebview recursively traverses public attributes and attempts to inspect
        # window.native (a COM WebView2 control), which can hang Windows and trigger
        # maximum-recursion-depth / wrong-UI-thread errors.
        self._window = None
    def pick_folder(self):
        try:
            import webview
            chosen=self._window.create_file_dialog(webview.FOLDER_DIALOG)
            return str(chosen[0]) if chosen else ''
        except Exception:return ''
    def pick_imdb(self):
        try:
            import webview
            chosen=self._window.create_file_dialog(webview.OPEN_DIALOG,file_types=('IMDb dataset (*.tsv;*.gz)','All files (*.*)'))
            return str(chosen[0]) if chosen else ''
        except Exception:return ''
    def pick_backup(self):
        try:
            import webview
            chosen=self._window.create_file_dialog(webview.OPEN_DIALOG,file_types=('MovieVault Backup (*.zip)','All files (*.*)'))
            return str(chosen[0]) if chosen else ''
        except Exception:return ''

def run_app(data_dir=None, browser=False, port=0):
    # Apply only a previously approved and validated import before opening SQLite.
    apply_pending_migration(data_dir or default_data_dir())
    cat=Catalog(data_dir)
    cat.process_pending_restore()
    cat.initialize()
    server=MovieServer(cat,port)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:
        if not browser:
            try:
                import webview
                api=DesktopApi()
                window=webview.create_window('MovieVault',server.url,width=1510,height=930,min_size=(1010,670),background_color='#080f19',js_api=api)
                api._window=window
                webview.start(debug=False,private_mode=True)
                return
            except ImportError:
                if getattr(sys,'frozen',False):
                    raise RuntimeError('Desktop WebView unavailable. Install Microsoft Edge WebView2 Runtime and restart MovieVault.')
            except Exception as e:
                if getattr(sys,'frozen',False):
                    raise RuntimeError('Desktop WebView failed. Install/repair Microsoft Edge WebView2 Runtime. '+str(e)) from e
        webbrowser.open(server.url)
        print('MovieVault URL:',server.url,'\nData folder:',cat.dir,'\nPress Ctrl+C to stop.')
        t.join()
    except KeyboardInterrupt:pass
    finally:server.shutdown();server.server_close()

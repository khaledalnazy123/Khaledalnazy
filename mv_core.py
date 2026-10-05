"""MovieVault: resilient local movie catalog. Python 3.10+; no network needed for scanning."""
from __future__ import annotations
import csv, gzip, hashlib, io, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, threading, time, unicodedata, urllib.parse, urllib.request, urllib.error, zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from PIL import Image, ImageOps, UnidentifiedImageError
from mv_tmdb import CredentialStore,TMDbClient,TMDbError
from mv_diagnostics import Diagnostics
from mv_gemini import GeminiCredentials,GeminiClient,GeminiError

VERSION = '2.0.0-rc.2'
VIDEO_EXTS = {'.mkv','.mp4','.m4v','.avi','.mov','.wmv','.webm','.mpg','.mpeg','.ts','.m2ts','.flv'}
SUB_EXTS = {'.srt','.sub','.idx','.ass','.ssa','.sup','.vtt','.smi','.ttml','.pgs'}
POSTER_NAMES = ('poster.jpg','poster.jpeg','poster.png','folder.jpg','folder.png','movie poster.jpg','cover.jpg','cover.png')
GROUPS = ('YTS','YIFY','RARBG','QXR','PSA','EVO','FGT','SPARKS','FLUX','NTB','AMZN','Tigole','Joy','MZABI','GalaxyRG','MeGusta','ION10','CtrlHD','DON','EPSiLON','RZE','HDS')
LANGS = {'ar':'Arabic','ara':'Arabic','arabic':'Arabic','en':'English','eng':'English','english':'English','fr':'French','fre':'French','fra':'French','es':'Spanish','spa':'Spanish','de':'German','ger':'German','it':'Italian'}
SCHEMA_VERSION = 3
BACKUP_MAX_ARCHIVE_BYTES = 1_200_000_000
BACKUP_MAX_UNCOMPRESSED_BYTES = 1_200_000_000
BACKUP_MAX_DATABASE_BYTES = 1_000_000_000
BACKUP_MAX_POSTER_BYTES = 12_000_000
BACKUP_REQUIRED_TABLES = frozenset({'meta','roots','movies','subtitles','settings','imdb_titles'})

def normalize(v: str) -> str:
    v = unicodedata.normalize('NFKD', v or '').casefold()
    v = ''.join(c for c in v if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9\u0600-\u06ff]+',' ',v).strip()

def clean_year(v):
    try:
        y=int(v)
        return y if 1870 <= y <= 2100 else None
    except (ValueError, TypeError): return None

def parse_filename(name: str) -> dict:
    stem=Path(name).stem
    yr=re.search(r'(?<!\d)(18\d\d|19\d\d|20\d\d)(?!\d)',stem)
    title=stem[:yr.start()] if yr else re.split(r'(?i)(?:[\[\( ](?:2160p|1080p|720p|480p|4k|bluray|brrip|web[- .]?dl|webrip|dvdrip|hdtv|remux)\b)',stem,maxsplit=1)[0]
    title=re.sub(r'[._]+',' ',title)
    title=re.sub(r'[\s\[\]{}()\-]+$','',title).strip()
    if not title: title=re.sub(r'[._]',' ',stem).strip() or stem
    r=re.search(r'(?i)\b(2160p|1080p|720p|480p|4k)\b',stem)
    resolution=({'2160p':'4K','4k':'4K'}).get(r.group(1).lower(),r.group(1).lower()) if r else ''
    source=''
    for pat,val in [(r'(?i)\bblu[ ._-]?ray\b','BluRay'),(r'(?i)\bremux\b','Remux'),(r'(?i)\bweb[ ._-]?dl\b','WEB-DL'),(r'(?i)\bwebrip\b','WEBRip'),(r'(?i)\bbrrip\b','BRRip'),(r'(?i)\bhdtv\b','HDTV'),(r'(?i)\bdvdrip\b','DVDRip')]:
        if re.search(pat,stem): source=val;break
    grp=''
    for name_ in GROUPS:
        if re.search(r'(?i)(?<![a-z0-9])'+re.escape(name_)+r'(?![a-z0-9])',stem): grp=name_;break
    if not grp:
        last=re.search(r'(?i)(?:-|\[)([A-Za-z][A-Za-z0-9]{1,16})\]?$' ,stem)
        if last and last.group(1).upper() not in {'X264','X265','H264','H265','AAC','DTS','AC3','TRUEHD','ATMOS','BLURAY'}: grp=last.group(1)
    return {'title':title,'year':int(yr.group(1)) if yr else None,'resolution_tag':resolution,'source':source,'release_group':grp}

def file_fingerprint(path:Path) -> str:
    h=hashlib.sha256(); st=path.stat();h.update(str(st.st_size).encode())
    with path.open('rb') as f:
        h.update(f.read(65536))
        if st.st_size>131072:
            f.seek(max(0,st.st_size//2-32768));h.update(f.read(65536))
        if st.st_size>65536:
            f.seek(max(0,st.st_size-65536));h.update(f.read(65536))
    return h.hexdigest()

def find_ffmpeg() -> str|None:
    exe='ffmpeg.exe' if os.name=='nt' else 'ffmpeg'
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    for location in (base/'vendor'/exe,Path(__file__).parent/'vendor'/exe):
        if location.is_file():return str(location)
    return shutil.which(exe)

def find_ffprobe() -> str|None:
    exe='ffprobe.exe' if os.name=='nt' else 'ffprobe'
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    candidates=[base/'vendor'/exe,Path(__file__).parent/'vendor'/exe]
    for c in candidates:
        if c.is_file():return str(c)
    return shutil.which(exe)

def probe_media(path:Path, ffprobe=None) -> dict:
    exe=ffprobe if ffprobe is not None else find_ffprobe()
    if not exe: return {'probe_error':'ffprobe unavailable','streams':[],'format':{}}
    try:
        p=subprocess.run([str(exe),'-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,timeout=25,creationflags=(subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        if p.returncode: return {'probe_error':p.stderr.strip()[:250] or 'ffprobe failed','streams':[],'format':{}}
        data=json.loads(p.stdout)
        return {'format':data.get('format',{}),'streams':data.get('streams',[])}
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:
        return {'probe_error':str(e)[:250],'streams':[],'format':{}}

def media_summary(raw:dict, stat_size:int, hints:dict) ->dict:
    fm=raw.get('format') or {}; streams=raw.get('streams') or []
    videos=[s for s in streams if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')]
    audios=[s for s in streams if s.get('codec_type')=='audio']
    subs=[s for s in streams if s.get('codec_type')=='subtitle']
    videos.sort(key=lambda x:int(x.get('disposition',{}).get('default') or 0),reverse=True)
    audios.sort(key=lambda x:int(x.get('disposition',{}).get('default') or 0),reverse=True)
    v=videos[0] if videos else {}; a=audios[0] if audios else {}
    def num(x):
        try: return float(x)
        except (ValueError,TypeError,OverflowError):return None
    d=num(fm.get('duration')); ob=num(fm.get('bit_rate'))
    if not ob and d and d>0:ob=stat_size*8/d; overall_est=True
    else: overall_est=False
    vb=num(v.get('bit_rate')); ab=num(a.get('bit_rate'))
    # Fallback estimate of video only when a single video and audio stream exists.
    video_est=False
    if not vb and ob and len(videos)==1 and len(audios)==1 and ab:
        vb=max(0,ob-ab);video_est=True
    w=v.get('width');h=v.get('height')
    res=(f'{w} × {h}' if w and h else hints['resolution_tag'])
    # A filename can claim 4K even when its real encoded resolution is smaller.
    if w and h:
        label=('4K' if w>=3400 or h>=2000 else '1080p' if w>=1700 or h>=1000 else '720p' if w>=1200 or h>=700 else '480p' if w>=700 or h>=470 else 'SD')
    else:label=hints['resolution_tag']
    hdr=v.get('color_transfer','') in ('smpte2084','arib-std-b67')
    return {'size_bytes':stat_size,'duration':d,'resolution':res or '', 'resolution_tag':label,'resolution_verified':int(bool(w and h)),'width':w,'height':h,
            'video_codec':v.get('codec_name') or '', 'video_bitrate':round(vb) if vb else None,
            'video_bitrate_estimated':video_est,'audio_codec':a.get('codec_name') or '',
            'audio_bitrate':round(ab) if ab else None,'overall_bitrate':round(ob) if ob else None,
            'overall_bitrate_estimated':overall_est,'channels':a.get('channels'),'audio_layout':a.get('channel_layout',''),
            'fps':v.get('avg_frame_rate') or '', 'hdr':int(hdr),'audio_streams':len(audios),
            'video_streams':len(videos),'subtitle_streams':len(subs),'container':fm.get('format_long_name') or fm.get('format_name',''),
            'probe_error':raw.get('probe_error','')}

def default_data_dir() -> Path:
    env=os.environ.get('MOVIEVAULT_DATA_DIR')
    if env:return Path(env).expanduser().resolve()
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')/'MovieVault'/'v2'
    return Path.home()/'.local'/'share'/'MovieVault'/'v2'

class BusyError(Exception):pass
class ValidationError(Exception):pass

def _copy_limited(source,destination,max_bytes:int) -> int:
    total=0
    while True:
        chunk=source.read(min(1024*1024,max_bytes-total+1))
        if not chunk:break
        total+=len(chunk)
        if total>max_bytes:raise ValidationError('Backup content exceeds safety limit')
        destination.write(chunk)
    return total

def _validate_restore_database(path:Path,manifest_schema:int) -> None:
    try:
        uri=f'{path.resolve().as_uri()}?mode=ro'
        db=sqlite3.connect(uri,uri=True,timeout=15)
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            integrity=[r[0] for r in db.execute('PRAGMA integrity_check').fetchall()]
            if integrity!=['ok']:raise ValidationError('Backup database failed integrity check')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not BACKUP_REQUIRED_TABLES <= tables:raise ValidationError('Backup database is missing required tables')
            row=db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if not row:raise ValidationError('Backup database has no schema version')
            db_schema=int(row[0])
            if not 1<=db_schema<=SCHEMA_VERSION or db_schema!=manifest_schema:
                raise ValidationError('Backup database schema does not match its manifest')
        finally:
            db.close()
    except ValidationError:raise
    except (sqlite3.DatabaseError,ValueError,OSError) as exc:
        raise ValidationError('Backup database is corrupt or unreadable') from exc

class Catalog:
    def __init__(self,data_dir:Path|str|None=None):
        self.dir=Path(data_dir or default_data_dir());self.dir.mkdir(parents=True,exist_ok=True)
        self.posters=self.dir/'posters';self.posters.mkdir(exist_ok=True)
        self.backups=self.dir/'backups';self.backups.mkdir(exist_ok=True)
        self.db=self.dir/'movievault.sqlite'
        self.tmdb_credentials=CredentialStore(self.dir)
        self.gemini_credentials=GeminiCredentials(self.dir)
        self.diagnostics=Diagnostics(self.dir)
        self.job_lock=threading.Lock();self.jobs={};self.active_job=None
        self.initialize()
        # Older v2 builds could activate a v1 snapshot before removing arbitrary
        # legacy settings. Clean only catalogs marked as v1 imports, once, before
        # any API response or backup can expose/copy those rows.
        from mv_migration import cleanup_migrated_v2_database
        removed_legacy_settings=cleanup_migrated_v2_database(self.db)
        if removed_legacy_settings:
            self.diagnostics.event('legacy_settings_sanitized',removed_count=removed_legacy_settings)
        self.expire_tmdb_artwork()
        self.expire_tmdb_details()
        self.diagnostics.event('app_initialized',schema=SCHEMA_VERSION)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(str(self.db),timeout=45)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA busy_timeout=45000');db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA journal_mode=WAL')
        try:
            yield db;db.commit()
        except Exception:
            db.rollback();raise
        finally:db.close()
    def initialize(self):
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS roots(id INTEGER PRIMARY KEY,path TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,last_scan TEXT,last_status TEXT DEFAULT 'unscanned');
            CREATE TABLE IF NOT EXISTS movies(
                id INTEGER PRIMARY KEY,root_id INTEGER NOT NULL,relative_path TEXT NOT NULL,original_filename TEXT NOT NULL,
                current_filename TEXT NOT NULL,display_title TEXT NOT NULL,year INTEGER,genres TEXT DEFAULT '',imdb_id TEXT DEFAULT '',imdb_rating REAL,
                source TEXT DEFAULT '',release_group TEXT DEFAULT '',resolution_tag TEXT DEFAULT '',resolution_verified INTEGER DEFAULT 0,
                size_bytes INTEGER DEFAULT 0,duration REAL,resolution TEXT DEFAULT '',width INTEGER,height INTEGER,
                video_codec TEXT DEFAULT '',video_bitrate INTEGER,video_bitrate_estimated INTEGER DEFAULT 0,
                audio_codec TEXT DEFAULT '',audio_bitrate INTEGER,overall_bitrate INTEGER,overall_bitrate_estimated INTEGER DEFAULT 0,
                channels INTEGER,audio_layout TEXT DEFAULT '',fps TEXT DEFAULT '',hdr INTEGER DEFAULT 0,
                audio_streams INTEGER DEFAULT 0,video_streams INTEGER DEFAULT 0,subtitle_streams INTEGER DEFAULT 0,container TEXT DEFAULT '',
                probe_error TEXT DEFAULT '',raw_probe TEXT DEFAULT '{}',fingerprint TEXT DEFAULT '',status TEXT DEFAULT 'available',
                added_at TEXT NOT NULL,last_seen TEXT NOT NULL,modified_ns INTEGER DEFAULT 0,
                poster_path TEXT DEFAULT '',poster_source TEXT DEFAULT '',poster_credit TEXT DEFAULT '',poster_locked INTEGER DEFAULT 0,poster_attempted_at TEXT DEFAULT '',
                subtitle_source TEXT DEFAULT 'Unknown',translation_quality TEXT DEFAULT 'Unrated',notes TEXT DEFAULT '',watched INTEGER DEFAULT 0,
                manual_fields TEXT DEFAULT '[]',UNIQUE(root_id,relative_path),FOREIGN KEY(root_id) REFERENCES roots(id));
            CREATE INDEX IF NOT EXISTS movies_status_idx ON movies(status);
            CREATE INDEX IF NOT EXISTS movies_title_idx ON movies(display_title);
            CREATE INDEX IF NOT EXISTS movies_fp_idx ON movies(fingerprint);
            CREATE TABLE IF NOT EXISTS subtitles(id INTEGER PRIMARY KEY,movie_id INTEGER NOT NULL,kind TEXT NOT NULL,filename TEXT NOT NULL,format TEXT NOT NULL,language TEXT DEFAULT 'Unknown',stream_index INTEGER,source TEXT DEFAULT 'Unknown',quality TEXT DEFAULT 'Unrated',UNIQUE(movie_id,kind,filename),FOREIGN KEY(movie_id) REFERENCES movies(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS imdb_titles(tconst TEXT PRIMARY KEY,title_norm TEXT NOT NULL,primary_title TEXT NOT NULL,year INTEGER,genres TEXT,runtime INTEGER);
            CREATE INDEX IF NOT EXISTS imdb_title_norm_idx ON imdb_titles(title_norm,year);
            CREATE TABLE IF NOT EXISTS imdb_ratings(tconst TEXT PRIMARY KEY,rating REAL,votes INTEGER);
            ''')
            row=c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row and int(row['value'])>SCHEMA_VERSION:raise RuntimeError('This library belongs to a newer MovieVault version. Refusing to modify it.')
            # Safe additive migrations for earlier preview databases (never drop old data).
            existing={r['name'] for r in c.execute('PRAGMA table_info(movies)')}
            for name,definition in {
                'poster_attempted_at':"TEXT DEFAULT ''",
                'resolution_verified':'INTEGER DEFAULT 0',
                'tmdb_id':'INTEGER', 'cast_names':"TEXT DEFAULT ''", 'overview':"TEXT DEFAULT ''", 'tmdb_rating':'REAL', 'tmdb_metadata_at':"TEXT DEFAULT ''",
                'personal_rating':'REAL', 'favorite':'INTEGER DEFAULT 0',
                'preferred_subtitle_id':'INTEGER', 'playback_preference':"TEXT DEFAULT 'auto'"
            }.items():
                if name not in existing:c.execute(f'ALTER TABLE movies ADD COLUMN {name} {definition}')
            subtitlecols={r['name'] for r in c.execute('PRAGMA table_info(subtitles)')}
            for name,definition in {'language_manual':'INTEGER DEFAULT 0','translator':"TEXT DEFAULT ''"}.items():
                if name not in subtitlecols:c.execute(f'ALTER TABLE subtitles ADD COLUMN {name} {definition}')
            c.execute('CREATE TABLE IF NOT EXISTS subtitle_sources(name TEXT PRIMARY KEY,created_at TEXT NOT NULL)')
            c.execute("CREATE TABLE IF NOT EXISTS ai_suggestions(movie_id INTEGER PRIMARY KEY,suggested_title TEXT,suggested_year INTEGER,suggested_imdb_id TEXT,reason TEXT,status TEXT,created_at TEXT)")
            if row and int(row['value'])<2:
                c.execute("UPDATE movies SET resolution_tag=CASE WHEN width>=3400 OR height>=2000 THEN '4K' WHEN width>=1700 OR height>=1000 THEN '1080p' WHEN width>=1200 OR height>=700 THEN '720p' WHEN width>=700 OR height>=470 THEN '480p' ELSE 'SD' END,resolution_verified=1 WHERE width IS NOT NULL AND height IS NOT NULL")
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",(str(SCHEMA_VERSION),))
            for k,v in {'auto_posters':'1','poster_in_folder':'1','archive_missing':'1','auto_imdb':'1','poster_provider':'commons','default_external_subtitle_lang':'Arabic','theme':'dark','auto_frame_fallback':'0','auto_gemini_fallback':'0','gemini_model':''}.items():
                c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
            for r in c.execute("SELECT id,poster_path FROM movies WHERE poster_path<>''").fetchall():
                expected=(self.dir/r['poster_path']).resolve()
                if expected.parent!=self.posters.resolve() or not expected.is_file():
                    c.execute("UPDATE movies SET poster_path='',poster_source='',poster_credit='',poster_locked=0,poster_attempted_at='' WHERE id=?",(r['id'],))
    def expire_tmdb_artwork(self):
        from datetime import datetime,timezone,timedelta
        cutoff=datetime.now(timezone.utc)-timedelta(days=170)
        old=[]
        with self.connect() as c:
            for r in c.execute("SELECT id,poster_attempted_at,poster_path FROM movies WHERE poster_source='TMDb'").fetchall():
                try:date=datetime.fromisoformat(r['poster_attempted_at']).astimezone(timezone.utc)
                except (ValueError,TypeError):date=datetime.min.replace(tzinfo=timezone.utc)
                if date < cutoff:
                    old.append(r['id'])
                    c.execute("UPDATE movies SET poster_path='',poster_source='',poster_credit='',poster_attempted_at='' WHERE id=?",(r['id'],))
        for mid in old:
            path=self.posters/f'{mid}.jpg'
            if not path.is_symlink():path.unlink(missing_ok=True)
    def settings(self):
        with self.connect() as c:return {r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}
    def set_settings(self,items:dict):
        allowed={'auto_posters','poster_in_folder','archive_missing','auto_imdb','poster_provider','default_external_subtitle_lang','theme','auto_frame_fallback','auto_gemini_fallback','gemini_model'}
        if set(items)-allowed:raise ValidationError('Unknown setting')
        with self.connect() as c:
            for k,v in items.items():
                if k=='poster_provider' and v not in ('commons','tmdb','none'):raise ValidationError('Unknown poster provider')
                if k=='poster_provider' and v=='tmdb' and not self.tmdb_credentials.get():raise ValidationError('Connect TMDB in Settings before enabling it')
                if k=='gemini_model':
                    if v and (not re.fullmatch(r'[A-Za-z0-9._-]{3,90}',str(v)) or str(v) not in GeminiClient(self.gemini_credentials.get()).models()):raise ValidationError('Select an available Gemini model')
                elif k=='default_external_subtitle_lang' and str(v) not in ('Arabic','English','Unknown'):raise ValidationError('Invalid default subtitle language')
                elif k=='theme' and str(v) not in ('dark','light','midnight'):raise ValidationError('Invalid interface theme')
                elif k not in ('poster_provider','default_external_subtitle_lang','theme','gemini_model') and str(v) not in ('0','1'):raise ValidationError('Expected 0 or 1')
                c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,str(v)))
        self.diagnostics.event('settings_changed',fields=','.join(sorted(items)))
        return self.settings()
    def gemini_status(self):
        return {'connected':bool(self.gemini_credentials.get()),'model':self.settings().get('gemini_model','')}
    def connect_gemini(self,key):
        # Validate before storing; never return the key to browser, DB, backup or log.
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{25,160}',key):raise ValidationError('Invalid Gemini API key')
        try:models=GeminiClient(key).models()
        except GeminiError as exc:raise ValidationError(str(exc)) from None
        self.gemini_credentials.save(key)
        selected=next((n for n in models if 'flash' in n.lower()),models[0])
        with self.connect() as c:c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('gemini_model',?)",(selected,))
        return {'connected':True,'model':selected,'models':models}
    def disconnect_gemini(self):
        self.gemini_credentials.clear()
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('gemini_model','')")
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('auto_gemini_fallback','0')")
        return self.gemini_status()
    def _resolve_ai_impl(self,job,mid):
        # Gemini suggestion is explicitly opted-in at the movie level; TMDB is authoritative verification.
        movie=self.movie(mid)
        if not self.gemini_credentials.get():raise ValidationError('Connect Gemini in Settings first')
        if not self.tmdb_credentials.get():raise ValidationError('Connect TMDB for independent verification of Gemini suggestions')
        if movie.get('imdb_id') and re.fullmatch(r'tt\d{5,12}',movie['imdb_id']):
            job['message']='This movie already has an IMDb ID; AI not needed.'
            return {'verified':True,'unchanged':True,'imdb_id':movie['imdb_id']}
        model=self.settings().get('gemini_model','')
        suggestion=GeminiClient(self.gemini_credentials.get()).identify(movie['display_title'],movie['year'],model)
        status='unverified';verified_id='';tmdb_id=None;extra=''
        try:
            # Independent verification against a canonical movie result and its external ID.
            result,method=TMDbClient(self.tmdb_credentials.get()).match(suggestion['title'],suggestion['year'] or movie['year'],suggestion['imdb_id'])
            name_norms={normalize(result.get('title','')),normalize(result.get('original_title',''))}
            if normalize(suggestion['title']) not in name_norms:raise ValidationError('Suggested title differs from TMDB match')
            date=result.get('release_date') or ''
            if suggestion['year'] and (len(date)<4 or date[:4]!=str(suggestion['year'])):raise ValidationError('Suggested year does not match TMDB')
            data=TMDbClient(self.tmdb_credentials.get()).details(int(result['id']))
            imdb=(data.get('external_ids') or {}).get('imdb_id') or data.get('imdb_id') or ''
            if not re.fullmatch(r'tt\d{5,12}',imdb):raise ValidationError('TMDB did not confirm an IMDb ID')
            if suggestion['imdb_id'] and suggestion['imdb_id']!=imdb:raise ValidationError('Gemini IMDb ID disagrees with TMDB')
            if suggestion['uncertain']:raise ValidationError('AI itself flagged this result as uncertain')
            status='verified';verified_id=imdb;tmdb_id=int(result['id'])
        except (TMDbError,ValidationError,ValueError,TypeError) as exc:extra=str(exc)[:150]
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO ai_suggestions VALUES(?,?,?,?,?,?,?)',
                      (mid,suggestion['title'],suggestion['year'],suggestion['imdb_id'],suggestion['reason']+' '+extra,status,time.strftime('%Y-%m-%dT%H:%M:%S%z')))
            if status=='verified':
                locks=set(movie['manual_fields']);fields={'tmdb_id':tmdb_id}
                if 'display_title' not in locks:fields['display_title']=suggestion['title']
                if 'year' not in locks and suggestion['year']:fields['year']=suggestion['year']
                if 'imdb_id' not in locks:fields['imdb_id']=verified_id
                rating=c.execute('SELECT rating FROM imdb_ratings WHERE tconst=?',(verified_id,)).fetchone()
                if rating:fields['imdb_rating']=rating['rating']
                row=c.execute('SELECT genres FROM imdb_titles WHERE tconst=?',(verified_id,)).fetchone()
                if row and 'genres' not in locks:fields['genres']=row['genres']
                c.execute('UPDATE movies SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',list(fields.values())+[mid])
        job['message']='Gemini suggested a title; '+('independently verified by TMDB.' if status=='verified' else 'needs manual review.')
        return {'verified':status=='verified','suggestion':suggestion,'imdb_id':verified_id,'reason':extra}
    def resolve_ai(self,mid):return self.start_job('ai_identify',lambda job:self._resolve_ai_impl(job,int(mid)))
    def subtitle_sources(self):
        with self.connect() as c:
            custom=[r['name'] for r in c.execute('SELECT name FROM subtitle_sources ORDER BY name COLLATE NOCASE')]
        standard=['Unknown','Netflix','OSN','Amazon Prime Video','Disney+','BluRay','WEB-DL','Manual','Other']
        return list(dict.fromkeys(standard+custom))
    def add_subtitle_source(self,name):
        name=str(name or '').strip()
        if not (2<=len(name)<=70) or any(ord(c)<32 for c in name):raise ValidationError('Custom subtitle source must contain 2–70 printable characters')
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO subtitle_sources(name,created_at) VALUES(?,?)',(name,time.strftime('%Y-%m-%dT%H:%M:%S%z')))
        return self.subtitle_sources()
    def remove_subtitle_source(self,name):
        with self.connect() as c:c.execute('DELETE FROM subtitle_sources WHERE name=?',(str(name),))
        # Historical subtitle annotations keep their old source value.
        return self.subtitle_sources()
    def tmdb_status(self):
        return {'connected':bool(self.tmdb_credentials.get()),'provider':self.settings().get('poster_provider','commons')}
    def connect_tmdb(self,token):
        # Never save or return the credential until the official endpoint confirms it is valid.
        if not isinstance(token,str) or not 25<=len(token)<=2048 or any(x.isspace() for x in token):
            raise ValidationError('Enter the API Read Access Token from TMDB Settings')
        try:TMDbClient(token).test_connection()
        except TMDbError as e:raise ValidationError(str(e)) from None
        self.tmdb_credentials.save(token)
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('poster_provider','tmdb')")
            # Prior unsuccessful Wikimedia attempts should be eligible for TMDB retrieval.
            c.execute("UPDATE movies SET poster_attempted_at='' WHERE (poster_path='' OR poster_path IS NULL) AND poster_locked=0")
        return self.tmdb_status()
    def disconnect_tmdb(self):
        self.tmdb_credentials.clear()
        with self.connect() as c:c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('poster_provider','commons')")
        return self.tmdb_status()
    def roots(self):
        with self.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM roots WHERE enabled=1 ORDER BY id DESC')]
    def add_root(self,path):
        p=Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
        if not p.is_dir():raise ValidationError('The folder is not accessible. Connect the drive and try again.')
        with self.connect() as c:
            c.execute("INSERT INTO roots(path,enabled,last_status) VALUES(?,1,'unscanned') ON CONFLICT(path) DO UPDATE SET enabled=1",(str(p),))
            return dict(c.execute('SELECT * FROM roots WHERE path=?',(str(p),)).fetchone())
    def disable_root(self,root_id:int):
        with self.connect() as c:
            if not c.execute('SELECT 1 FROM roots WHERE id=?',(root_id,)).fetchone():raise ValidationError('Root not found')
            c.execute("UPDATE roots SET enabled=0,last_status='disabled' WHERE id=?",(root_id,))
            c.execute("UPDATE movies SET status='offline' WHERE root_id=?",(root_id,))
    def stats(self):
        with self.connect() as c:
            r=c.execute("SELECT COUNT(*) total,COALESCE(SUM(status='available'),0) available,COALESCE(SUM(status='missing'),0) missing,COALESCE(SUM(status='offline'),0) offline,COALESCE(SUM(CASE WHEN status='available' THEN size_bytes ELSE 0 END),0) disk_bytes,COALESCE(SUM(size_bytes),0) catalog_bytes,COUNT(DISTINCT NULLIF(release_group,'')) groups FROM movies").fetchone()
            imdb=c.execute('SELECT value FROM meta WHERE key=?',('imdb_imported_at',)).fetchone()
            ratings=c.execute('SELECT value FROM meta WHERE key=?',('imdb_ratings_at',)).fetchone()
            return {**dict(r),'imdb_imported_at':imdb['value'] if imdb else None,'imdb_ratings_at':ratings['value'] if ratings else None, 'ffprobe_found':bool(find_ffprobe())}
    def groups(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT release_group AS 'group',COUNT(*) AS count FROM movies WHERE release_group<>'' GROUP BY release_group ORDER BY count DESC,release_group COLLATE NOCASE LIMIT 100")]
    def movies(self,q='',status='',quality='',sort='recent',page=1,limit=54, genre='',subtitle_language='',subtitle_source='',translator='',actor='',year_from=None,year_to=None,favorite='',watched=''):
        page=max(1,int(page));limit=min(max(1,int(limit)),150)
        where=[];args=[]
        if q:
            where.append("(LOWER(display_title) LIKE ? ESCAPE '\\' OR LOWER(original_filename) LIKE ? ESCAPE '\\' OR LOWER(release_group) LIKE ? ESCAPE '\\' OR LOWER(genres) LIKE ? ESCAPE '\\' OR LOWER(cast_names) LIKE ? ESCAPE '\\' OR CAST(year AS TEXT) LIKE ? ESCAPE '\\')")
            key='%'+str(q).lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';args.extend([key]*6)
        if status in ('available','missing','offline'):where.append('status=?');args.append(status)
        if quality in ('4K','1080p','720p','480p'):where.append('resolution_tag=?');args.append(quality)
        if quality=='arabic_subs':where.append("EXISTS(SELECT 1 FROM subtitles s WHERE s.movie_id=movies.id AND s.language='Arabic')")
        if quality=='no_subs':where.append('NOT EXISTS(SELECT 1 FROM subtitles s WHERE s.movie_id=movies.id)')
        if quality=='poster_missing':where.append("(poster_path='' OR poster_path IS NULL)")
        if genre:
            genres=[str(g).strip().lower() for g in str(genre).split(',') if str(g).strip()][:10]
            if genres:
                where.append('('+ ' OR '.join("(','||REPLACE(LOWER(genres),' ','')||',') LIKE ?" for _ in genres)+')')
                args.extend([f'%,{g.replace(" ","")},%' for g in genres])
        if actor:where.append('LOWER(cast_names) LIKE ?');args.append('%'+str(actor).lower().replace('%','').replace('_','')+'%')
        # Use a SINGLE correlated subtitle row when combining language/source/translator.
        # Netflix English + OSN Arabic must not pass Netflix AND Arabic together.
        clauses=[];sargs=[]
        if subtitle_language:clauses.append('s.language=?');sargs.append(str(subtitle_language))
        if subtitle_source:clauses.append('s.source=? COLLATE NOCASE');sargs.append(str(subtitle_source))
        if translator:clauses.append('s.translator LIKE ?');sargs.append('%'+str(translator).replace('%','').replace('_','')+'%')
        if clauses:where.append('EXISTS(SELECT 1 FROM subtitles s WHERE s.movie_id=movies.id AND '+' AND '.join(clauses)+')');args.extend(sargs)
        for key,val,op in [('year_from',year_from,'>='),('year_to',year_to,'<=')]:
            if val not in ('',None):
                yr=clean_year(val)
                if yr is None:raise ValidationError('Invalid production year filter')
                where.append('year'+op+'?');args.append(yr)
        if favorite in ('1','0'):where.append('favorite=?');args.append(int(favorite))
        if watched in ('1','0'):where.append('watched=?');args.append(int(watched))
        order={'recent':'id DESC','title':'display_title COLLATE NOCASE ASC','year':'year DESC,display_title','size':'size_bytes DESC','group':'release_group COLLATE NOCASE,display_title','rating':'imdb_rating DESC,display_title'}.get(sort,'id DESC')
        wc=' WHERE '+' AND '.join(where) if where else ''
        with self.connect() as c:
            total=c.execute('SELECT COUNT(*) n FROM movies'+wc,args).fetchone()['n']
            rows=c.execute('''SELECT id,display_title,year,genres,release_group,resolution_tag,resolution_verified,
                status,size_bytes,poster_path,poster_locked,source,subtitle_source,watched,imdb_rating,favorite,
                (SELECT COUNT(*) FROM subtitles s WHERE s.movie_id=movies.id) sub_count,
                (SELECT COUNT(*) FROM subtitles s WHERE s.movie_id=movies.id AND s.language='Arabic') arabic_count,
                (SELECT COUNT(*) FROM subtitles s WHERE s.movie_id=movies.id AND s.language='English') english_count,
                (SELECT GROUP_CONCAT(DISTINCT source) FROM subtitles s WHERE s.movie_id=movies.id AND s.source NOT IN ('','Unknown')) subtitle_sources
                FROM movies'''+wc+' ORDER BY '+order+' LIMIT ? OFFSET ?',args+[limit,(page-1)*limit]).fetchall()
            return {'total':total,'page':page,'limit':limit,'items':[dict(r) for r in rows]}
    def movie(self,movie_id):
        with self.connect() as c:
            r=c.execute('SELECT m.*,r.path root_path FROM movies m JOIN roots r ON r.id=m.root_id WHERE m.id=?',(movie_id,)).fetchone()
            if not r:raise ValidationError('Movie not found')
            d=dict(r);d['subtitles']=[dict(s) for s in c.execute('SELECT * FROM subtitles WHERE movie_id=? ORDER BY kind,filename',(movie_id,))]
            d['path']=str(Path(d['root_path'])/d['relative_path']);d['manual_fields']=json.loads(d['manual_fields'])
            suggestion=c.execute('SELECT suggested_title,suggested_year,suggested_imdb_id,reason,status FROM ai_suggestions WHERE movie_id=?',(movie_id,)).fetchone()
            d['ai_suggestion']=dict(suggestion) if suggestion else None
            for sub in d['subtitles']:
                sub['path']=str(Path(d['path']).parent/sub['filename']) if sub['kind']=='external' else ''
            return d
    def patch_movie(self,movie_id:int,values:dict):
        allowed={'display_title','year','genres','imdb_id','release_group','source','subtitle_source','translation_quality','notes','watched','poster_locked','favorite','personal_rating','playback_preference','preferred_subtitle_id'}
        if not values or set(values)-allowed:raise ValidationError('Unsupported edit field')
        with self.connect() as c:
            old=c.execute('SELECT * FROM movies WHERE id=?',(movie_id,)).fetchone()
            if not old:raise ValidationError('Movie not found')
            locks=set(json.loads(old['manual_fields']))
            updates={}
            for k,v in values.items():
                if k=='imdb_id':
                    v=str(v).strip()
                    match=re.fullmatch(r'(?:https?://(?:www\.)?imdb\.com/title/)?(tt\d{5,12})/?',v)
                    if v and not match:raise ValidationError('IMDb ID must resemble tt1234567 or a valid IMDb title URL')
                    v=match.group(1) if match else ''
                elif k=='year':v=clean_year(v)
                elif k in ('watched','poster_locked','favorite'):v=int(bool(v))
                elif k=='personal_rating':
                    v=None if v in ('',None) else float(v)
                    if v is not None and not 0<=v<=10:raise ValidationError('Personal rating must be 0–10')
                elif k=='playback_preference':
                    if v not in ('auto','ask','none','selected'):raise ValidationError('Unknown playback preference')
                elif k=='preferred_subtitle_id':
                    v=None if v in ('',None) else int(v)
                    if v is not None and not c.execute('SELECT 1 FROM subtitles WHERE id=? AND movie_id=?',(v,movie_id)).fetchone():raise ValidationError('Selected subtitle does not belong to this movie')
                elif k in ('display_title','genres','release_group','source','subtitle_source','translation_quality','notes'):
                    v=str(v).strip()[:(4000 if k=='notes' else 180)]
                    if k=='display_title' and not v:raise ValidationError('Movie title cannot be empty')
                updates[k]=v;locks.add(k)
            updates['manual_fields']=json.dumps(sorted(locks))
            columns=','.join(f'{k}=?' for k in updates)
            c.execute(f'UPDATE movies SET {columns} WHERE id=?',list(updates.values())+[movie_id])
        self.diagnostics.event('movie_metadata_changed',movie_id=movie_id,fields=','.join(sorted(values)))
        return self.movie(movie_id)
    def patch_subtitle(self,sub_id:int,values:dict):
        if not values or set(values)-{'source','quality','language','translator'}:raise ValidationError('Subtitle edit not allowed')
        vals={k:str(v).strip()[:100] for k,v in values.items()}
        if 'language' in vals:
            if vals['language'] not in ('Arabic','English','French','Spanish','German','Italian','Unknown','Other'):raise ValidationError('Unsupported subtitle language')
            vals['language_manual']=1
        with self.connect() as c:
            if not c.execute('SELECT 1 FROM subtitles WHERE id=?',(sub_id,)).fetchone():raise ValidationError('Subtitle not found')
            c.execute('UPDATE subtitles SET '+','.join(k+'=?' for k in vals)+' WHERE id=?',list(vals.values())+[sub_id])
        self.diagnostics.event('subtitle_metadata_changed',subtitle_id=sub_id,fields=','.join(sorted(values)))
    def detect_subtitles(self,fp:Path,raw:dict,all_movies:int)->list:
        result=[]
        for s in raw.get('streams',[]):
            if s.get('codec_type')=='subtitle':
                tags=s.get('tags') or {};lang=LANGS.get((tags.get('language') or '').lower(),'Unknown')
                result.append(('embedded',f'Stream #{s.get("index")}: {tags.get("title",s.get("codec_name","Subtitle"))}',s.get('codec_name',''),lang,s.get('index')))
        # Only associate stray unmatched subtitle files when there is exactly one movie in its folder.
        try: entries=list(fp.parent.iterdir())
        except OSError:return result
        this=normalize(fp.stem);hints=parse_filename(fp.name);short=normalize(hints['title'])
        for p in entries:
            if not p.is_file() or p.is_symlink() or p.suffix.lower() not in SUB_EXTS:continue
            key=normalize(p.stem)
            matched=(all_movies==1 or key==this or key.startswith(this+' ') or key==short or key.startswith(short+' '))
            if not matched:continue
            bits=re.findall(r'[A-Za-z]+',p.stem.lower());lang=next((LANGS[b] for b in bits[::-1] if b in LANGS),self.settings().get('default_external_subtitle_lang','Arabic'))
            result.append(('external',p.name,p.suffix[1:].upper(),lang,None))
        return result
    def _sync_subtitles(self,c,mid:int,detected:list):
        # Preserve source and quality notes for an unchanged subtitle file/stream.
        existing={(s['kind'],s['filename']):dict(s) for s in c.execute('SELECT * FROM subtitles WHERE movie_id=?',(mid,))}
        keep=set()
        for kind,name_,fmt,lang,stream_index in detected:
            key=(kind,name_);keep.add(key);ex=existing.get(key)
            if ex:c.execute('UPDATE subtitles SET format=?,language=?,stream_index=? WHERE id=?',(fmt,ex['language'] if ex.get('language_manual') else lang,stream_index,ex['id']))
            else:c.execute('INSERT OR IGNORE INTO subtitles(movie_id,kind,filename,format,language,stream_index) VALUES(?,?,?,?,?,?)',(mid,kind,name_,fmt,lang,stream_index))
        for key,ex in existing.items():
            if key not in keep:c.execute('DELETE FROM subtitles WHERE id=?',(ex['id'],))
    def _match_imdb(self,c,title,year):
        n=normalize(title)
        if not n:return None
        if year:
            r=c.execute('SELECT * FROM imdb_titles WHERE title_norm=? AND year=? LIMIT 2',(n,year)).fetchall()
            if len(r)==1:return dict(r[0])
            return None # never falsely assign a different year's movie
        r=c.execute('SELECT * FROM imdb_titles WHERE title_norm=? LIMIT 2',(n,)).fetchall()
        return dict(r[0]) if len(r)==1 else None
    def _scan_impl(self,job,root_ids=None):
        with self.connect() as c:
            roots=[dict(r) for r in c.execute('SELECT * FROM roots WHERE enabled=1 ORDER BY id')]
        if root_ids is not None: roots=[r for r in roots if r['id'] in set(root_ids)]
        ff=find_ffprobe(); settings=self.settings(); counts={'added':0,'updated':0,'unchanged':0,'missing':0,'offline':0,'failed_files':0,'posters_found':0,'posters_downloaded':0}
        for root in roots:
            if job.get('cancel'):break
            rid=root['id'];p=Path(root['path'])
            if not p.is_dir():
                with self.connect() as c:
                    c.execute("UPDATE roots SET last_status='offline' WHERE id=?",(rid,))
                    c.execute("UPDATE movies SET status='offline' WHERE root_id=?",(rid,))
                counts['offline']+=1;continue
            # Enumerate fully before marking entries missing; enumeration errors leave existing records untouched.
            media=[];failed=False
            def on_err(e):
                nonlocal failed
                failed=True;job['message']=f'Cannot fully inspect {e.filename}: {e.strerror}'
            try:
                for base,dirs,files in os.walk(p,topdown=True,followlinks=False,onerror=on_err):
                    dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
                    for name in files:
                        f=Path(base)/name
                        if f.suffix.lower() in VIDEO_EXTS and not f.is_symlink():media.append(f)
            except OSError:failed=True
            if failed:
                with self.connect() as c:c.execute("UPDATE roots SET last_status='scan_error' WHERE id=?",(rid,))
                counts['failed_files']+=1;continue
            seen=[]
            # map folder counts, allowing conservative subtitle association
            foldercounts={}
            for f in media:foldercounts[f.parent]=foldercounts.get(f.parent,0)+1
            job['total']+=len(media)
            for fp in media:
                if job.get('cancel'):
                    # Do not classify unseen files as Missing when a scan was cancelled.
                    break
                rel=str(fp.relative_to(p));job['message']=f'Scanning {fp.name[:80]}'
                try:
                    st=fp.stat();now=time.strftime('%Y-%m-%dT%H:%M:%S%z');fingerprint=None
                    unchanged_id=None
                    with self.connect() as c:
                        old=c.execute('SELECT * FROM movies WHERE root_id=? AND relative_path=?',(rid,rel)).fetchone()
                        if old and old['modified_ns']==st.st_mtime_ns and old['size_bytes']==st.st_size and old['status']=='available':
                            c.execute('UPDATE movies SET last_seen=? WHERE id=?',(now,old['id']))
                            # External subtitles and local poster.jpg can change even if video mtime is identical.
                            cached_raw=json.loads(old['raw_probe'] or '{}')
                            self._sync_subtitles(c,old['id'],self.detect_subtitles(fp,cached_raw,foldercounts[fp.parent]))
                            unchanged_id=old['id']
                    if unchanged_id is not None:
                        seen.append(unchanged_id);counts['unchanged']+=1;job['done']+=1
                        if self._local_poster(unchanged_id,fp,settings):counts['posters_found']+=1
                        continue
                    fingerprint=file_fingerprint(fp)
                    hints=parse_filename(fp.name);raw=probe_media(fp,ff);tech=media_summary(raw,st.st_size,hints)
                    with self.connect() as c:
                        if not old:
                            # only relink an unavailable movie if the content fingerprint is unique
                            # A renamed/moved file can still be marked Available until this scan finishes.
                            # Relink ONLY when its old physical path is gone and the fingerprint is unique.
                            candidates=c.execute("SELECT m.*,r.path AS candidate_root_path FROM movies m JOIN roots r ON r.id=m.root_id WHERE m.fingerprint=?",(fingerprint,)).fetchall()
                            absent=[x for x in candidates if not (Path(x['candidate_root_path'])/x['relative_path']).is_file()]
                            if len(absent)==1:old=absent[0]
                        locks=set(json.loads(old['manual_fields'])) if old else set()
                        fields={'root_id':rid,'relative_path':rel,'current_filename':fp.name,'last_seen':now,'modified_ns':st.st_mtime_ns,'fingerprint':fingerprint,'status':'available',**tech}
                        fields['raw_probe']=json.dumps(raw,ensure_ascii=False)
                        if not old:
                            fields.update({'original_filename':fp.name,'display_title':hints['title'],'year':hints['year'],'source':hints['source'],'release_group':hints['release_group'],'resolution_tag':tech['resolution_tag'],'added_at':now})
                        else:
                            for k,v in {'source':hints['source'],'release_group':hints['release_group'],'resolution_tag':tech['resolution_tag']}.items():
                                if k not in locks:fields[k]=v
                        if settings['auto_imdb']=='1':
                            hit=self._match_imdb(c,fields.get('display_title',old['display_title'] if old else ''),fields.get('year',old['year'] if old else None))
                            if hit:
                                rating=c.execute('SELECT rating FROM imdb_ratings WHERE tconst=?',(hit['tconst'],)).fetchone()
                                if rating:fields['imdb_rating']=rating['rating']
                                for k,v in {'year':hit['year'],'genres':hit['genres'],'imdb_id':hit['tconst']}.items():
                                    if k not in locks:fields[k]=v
                        if old:
                            # If the original row was at a different path, reconcile without replacing immutable first filename.
                            sql='UPDATE movies SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?'
                            c.execute(sql,list(fields.values())+[old['id']]);mid=old['id'];counts['updated']+=1
                        else:
                            sql='INSERT INTO movies('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')'
                            mid=c.execute(sql,list(fields.values())).lastrowid;counts['added']+=1
                        detected=self.detect_subtitles(fp,raw,foldercounts[fp.parent])
                        self._sync_subtitles(c,mid,detected)
                    seen.append(mid);job['done']+=1
                    if self._local_poster(mid,fp,settings):counts['posters_found']+=1
                    # Network artwork fetch is a separate job by design: scans should work offline and be responsive.
                except (OSError,sqlite3.Error,ValueError) as e:
                    # An unreadable existing file must not be misclassified as deleted.
                    if old:seen.append(old['id'])
                    counts['failed_files']+=1;job['done']+=1;job['message']=f'Skipped {fp.name}: {e}'
            if job.get('cancel'):
                with self.connect() as c:c.execute("UPDATE roots SET last_status='scan_cancelled' WHERE id=?",(rid,))
                break
            with self.connect() as c:
                if seen:
                    q=','.join('?' for _ in seen)
                    r=c.execute(f"UPDATE movies SET status='missing' WHERE root_id=? AND status IN ('available','offline') AND id NOT IN ({q})",[rid]+seen)
                else:r=c.execute("UPDATE movies SET status='missing' WHERE root_id=? AND status IN ('available','offline')",(rid,))
                counts['missing']+=r.rowcount
                c.execute("UPDATE roots SET last_status='online',last_scan=? WHERE id=?",(time.strftime('%Y-%m-%dT%H:%M:%S%z'),rid))
        job['result']=counts;job['message']='Scan completed; original file names and manual edits retained.'
        return counts
    def _refresh_local_metadata(self,job):
        matched=ratings=0
        with self.connect() as c:
            rows=c.execute('SELECT id,display_title,year,imdb_id,manual_fields FROM movies').fetchall()
            for r in rows:
                if job.get('cancel'):break
                locks=set(json.loads(r['manual_fields']))
                record_id=r['imdb_id'];hit=None
                if not record_id:
                    hit=self._match_imdb(c,r['display_title'],r['year'])
                    if hit:record_id=hit['tconst'];matched+=1
                changes={}
                if hit:
                    for k,v in {'imdb_id':hit['tconst'],'year':hit['year'],'genres':hit['genres']}.items():
                        if k not in locks:changes[k]=v
                if record_id:
                    rating=c.execute('SELECT rating FROM imdb_ratings WHERE tconst=?',(record_id,)).fetchone()
                    if rating:changes['imdb_rating']=rating['rating'];ratings+=1
                if changes:c.execute('UPDATE movies SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',list(changes.values())+[r['id']])
        return {'local_title_matches':matched,'ratings_refreshed':ratings}
    def _smart_update_impl(self,job,mode,include_gemini=False,limit=100):
        if mode not in ('quick','metadata','posters','full'):raise ValidationError('Unknown update mode')
        results={}
        if mode in ('quick','full') and not job.get('cancel'):
            results['scan']=self._scan_impl(job)
        if mode in ('metadata','full') and not job.get('cancel'):
            results['local_metadata']=self._refresh_local_metadata(job)
            if self.tmdb_credentials.get():
                with self.connect() as c:
                    ids=[r['id'] for r in c.execute("SELECT id FROM movies WHERE status='available' ORDER BY COALESCE(NULLIF(tmdb_metadata_at,''),'') ASC,id DESC LIMIT ?",(limit,)).fetchall()]
                report={'refreshed':0,'not_matched':0,'ai_verified':0,'ai_unverified':0}
                job['done']=0;job['total']=len(ids)
                for mid in ids:
                    if job.get('cancel'):break
                    job['message']=f'Refreshing metadata {job["done"]+1}/{job["total"]}'
                    try:self._refresh_movie_details_impl(job,mid);report['refreshed']+=1
                    except (TMDbError,ValidationError,urllib.error.URLError,TimeoutError):
                        report['not_matched']+=1
                        if include_gemini and self.gemini_credentials.get():
                            try:
                                result=self._resolve_ai_impl(job,mid)
                                report['ai_verified' if result.get('verified') else 'ai_unverified']+=1
                            except (ValidationError,GeminiError,TMDbError):pass
                    job['done']+=1
                    time.sleep(.12)
                results['online_metadata']=report
        if mode in ('posters','full') and not job.get('cancel'):
            if self.settings().get('poster_provider')!='none':results['posters']=self._poster_batch(job,min(50,limit))
        job['message']='Smart update completed or safely stopped; manually edited fields remain protected.'
        return results
    def smart_update(self,mode='quick',include_gemini=False,limit=100):
        lim=min(250,max(1,int(limit)))
        if include_gemini and not self.gemini_credentials.get():raise ValidationError('Connect Gemini before enabling AI fallback')
        return self.start_job('smart_update',lambda job:self._smart_update_impl(job,mode,bool(include_gemini),lim))
    def cancel_job(self,job_id):
        with self.job_lock:
            job=self.jobs.get(str(job_id))
            if not job or job['state']!='running':raise ValidationError('No running job with that ID')
            job['cancel']=True
            self.diagnostics.event('job_cancel_requested',job_id=str(job_id))
            return {'accepted':True,'message':'Cancellation requested; current file/network call may finish before stopping.'}
    def scan(self,root_ids=None):return self.start_job('scan',lambda j:self._scan_impl(j,root_ids))
    def start_job(self,kind,fn):
        with self.job_lock:
            if self.active_job and self.jobs.get(self.active_job,{}).get('state')=='running':raise BusyError('Another library operation is running')
            if len(self.jobs)>70:
                finished=sorted((v for v in self.jobs.values() if v['state']!='running'),key=lambda x:x.get('finished',0))
                for old in finished[:len(self.jobs)-60]:self.jobs.pop(old['id'],None)
            job_id=str(time.time_ns());job={'id':job_id,'type':kind,'state':'running','started':time.time(),'total':0,'done':0,'message':'Preparing…','result':None}
            self.jobs[job_id]=job;self.active_job=job_id
        def run():
            outcome='completed'
            try:
                job['result']=fn(job)
                outcome='cancelled' if job.get('cancel') else 'completed'
            except Exception as exc:
                outcome='failed';job['message']=f'{type(exc).__name__}: {exc}'
            finally:
                # Log before making completion visible to other threads/tests.
                # Diagnostics must not be allowed to crash the background worker.
                try:self.diagnostics.event('background_job_finished',kind=kind,state=outcome,job_id=job_id,done=job['done'])
                except OSError:pass
                job['finished']=time.time();job['state']=outcome
                # Queue online poster work separately, after file scanning has finished.
                if kind=='scan' and outcome=='completed' and self.settings()['auto_posters']=='1':
                    try:self.fetch_missing_posters(10)
                    except (BusyError,OSError):pass
        threading.Thread(target=run,daemon=True,name='mv-'+kind).start();return job_id
    def job(self,job_id):return dict(self.jobs.get(str(job_id),{'state':'not_found'}))
    def _poster_image(self,source,dest:Path):
        # PIL validates file contents; transcode to a single format. Reject decompression bombs.
        Image.MAX_IMAGE_PIXELS=35_000_000
        with Image.open(source) as im:
            im.load();im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1000,1500),Image.Resampling.LANCZOS)
            temp=dest.with_suffix('.partial');im.save(temp,'JPEG',quality=88,optimize=True);os.replace(temp,dest)
    def _local_poster(self,mid:int,fp:Path,settings:dict):
        with self.connect() as c:r=c.execute('SELECT poster_locked,poster_path FROM movies WHERE id=?',(mid,)).fetchone()
        if not r or r['poster_locked']:return False
        if r['poster_path'] and (self.dir/r['poster_path']).is_file():return False
        available={p.name.lower():p for p in fp.parent.iterdir() if p.is_file() and not p.is_symlink()}
        candidate=next((available[x] for x in POSTER_NAMES if x in available),None)
        if not candidate:return False
        dst=self.posters/f'{mid}.jpg'
        try:self._poster_image(candidate,dst)
        except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError):return False
        with self.connect() as c:c.execute('UPDATE movies SET poster_path=?,poster_source=? WHERE id=?',(f'posters/{mid}.jpg','local file',mid))
        return True
    def set_poster(self,mid:int,body:bytes,source='manual upload',credit=''):
        if len(body)>12_000_000 or not body:raise ValidationError('Poster must be a nonempty image under 12 MB')
        movie=self.movie(mid);dst=self.posters/f'{mid}.jpg'
        try:self._poster_image(io.BytesIO(body),dst)
        except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError) as e:raise ValidationError('Not a supported image') from e
        with self.connect() as c:c.execute('UPDATE movies SET poster_path=?,poster_source=?,poster_credit=?,poster_locked=?,poster_attempted_at=? WHERE id=?',(f'posters/{mid}.jpg',source,credit,1 if source in ('manual upload','Custom Frame') else 0,time.strftime('%Y-%m-%dT%H:%M:%S%z'),mid))
        if self.settings()['poster_in_folder']=='1' and movie['status']=='available' and source!='TMDb':
            try:
                folder=Path(movie['path']).parent;local=folder/'poster.jpg'
                # Atomic exclusive creation: do not follow a dangling poster.jpg symlink or overwrite user files.
                flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
                fd=os.open(local,flags,0o644)
                with os.fdopen(fd,'wb') as output,dst.open('rb') as source_file:
                    shutil.copyfileobj(source_file,output)
            except OSError:pass # cache always survives inaccessible/read-only movie folders
    def _frame_poster_impl(self,job,mid):
        movie=self.movie(mid)
        if movie['status']!='available' or not Path(movie['path']).is_file():raise ValidationError('Movie file is not available for generating a custom poster')
        if movie['poster_locked']:raise ValidationError('Unlock the existing manually selected poster before generating a replacement')
        executable=find_ffmpeg()
        if not executable:raise ValidationError('ffmpeg.exe is required for frame posters. Put it in vendor beside ffprobe.exe, or add it to PATH.')
        length=float(movie.get('duration') or 0)
        offset=max(10,min(240,length*.27)) if length>45 else 0
        command=[executable,'-hide_banner','-loglevel','error','-ss',str(round(offset,1)),'-i',movie['path'],'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1']
        proc=subprocess.run(command,capture_output=True,timeout=60,creationflags=(subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        if proc.returncode!=0 or not proc.stdout or len(proc.stdout)>18_000_000:raise ValidationError('Could not extract a safe representative movie frame')
        from PIL import ImageDraw,ImageFilter,ImageEnhance,ImageFont
        with Image.open(io.BytesIO(proc.stdout)) as original:
            original.load()
            if original.width<180 or original.height<100:raise ValidationError('Video frame is too small for a poster')
            source=original.convert('RGB')
            canvas=ImageOps.fit(source,(750,1125),method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(20))
            canvas=ImageEnhance.Brightness(canvas).enhance(.42)
            featured=source.copy();featured.thumbnail((710,575),Image.Resampling.LANCZOS)
            x=(750-featured.width)//2;y=145+(440-featured.height)//2
            canvas.paste(featured,(x,y))
            draw=ImageDraw.Draw(canvas)
            draw.rectangle((x-3,y-3,x+featured.width+3,y+featured.height+3),outline='#d8b76b',width=3)
            fontpath=next((str(f) for f in (Path('C:/Windows/Fonts/arialbd.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')) if f.is_file()),None)
            try:large=ImageFont.truetype(fontpath,48) if fontpath else ImageFont.load_default(size=48)
            except (OSError,TypeError):large=ImageFont.load_default()
            try:small=ImageFont.truetype(fontpath,23) if fontpath else ImageFont.load_default(size=23)
            except (OSError,TypeError):small=ImageFont.load_default()
            title=str(movie['display_title'])[:100];words=title.split();lines=[];line=''
            for word in words:
                attempt=(line+' '+word).strip()
                if draw.textbbox((0,0),attempt,font=large)[2]>665 and line:
                    lines.append(line);line=word
                else:line=attempt
            if line:lines.append(line)
            lines=lines[:3]
            y=700
            for line in lines:
                draw.text((375,y),line,fill='#fff5df',font=large,anchor='mt',stroke_width=1,stroke_fill='#18202b');y+=65
            label=f"{movie.get('year') or 'YEAR UNKNOWN'}  •  {movie.get('resolution_tag') or 'MOVIE'}"
            draw.text((375,min(970,y+35)),label,fill='#efc981',font=small,anchor='mt')
            draw.text((375,1074),'CUSTOM FRAME POSTER · NOT OFFICIAL ARTWORK',fill='#a9b4bf',font=small,anchor='mt')
            blob=io.BytesIO();canvas.save(blob,'JPEG',quality=89,optimize=True)
        self.set_poster(mid,blob.getvalue(),source='Custom Frame',credit='Generated locally from a frame of the user-provided video')
        job['message']='Custom poster generated locally without modifying movie or subtitle files.'
        return {'movie_id':mid,'source':'Custom Frame'}
    def generate_frame_poster(self,mid):return self.start_job('frame_poster',lambda job:self._frame_poster_impl(job,int(mid)))
    def _commons_poster(self,mid,job,replace=False):
        movie=self.movie(mid)
        if movie['poster_locked']:raise ValidationError('Poster locked by user')
        if not replace and movie['poster_path'] and (self.dir/movie['poster_path']).exists():raise ValidationError('Poster already exists. Use Refresh Poster Online to replace an unlocked automatic poster.')
        title=movie['display_title'];year=movie['year'];term=f'"{title}" film poster'+(f' {year}' if year else '')
        params={'action':'query','generator':'search','gsrsearch':term,'gsrnamespace':'6','gsrlimit':'10','prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':'800','format':'json','formatversion':'2'}
        url='https://commons.wikimedia.org/w/api.php?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'User-Agent':'MovieVault/1.0 (personal non-commercial local media catalog)'})
        with urllib.request.urlopen(req,timeout=10) as resp:data=json.load(io.TextIOWrapper(resp,encoding='utf-8'))
        pages=data.get('query',{}).get('pages',[]);norm=normalize(title)
        options=[]
        for page in pages:
            file_title=normalize(page.get('title',''))
            if norm not in file_title or not any(x in file_title for x in ('poster','film','movie')):continue
            infos=page.get('imageinfo',[])
            if not infos:continue
            info=infos[0];meta=info.get('extmetadata') or {}
            # Only use files with explicit reusable license; record attribution/source.
            license_url=(meta.get('LicenseUrl') or {}).get('value','');license_short=(meta.get('LicenseShortName') or {}).get('value','')
            artist=re.sub(r'<[^>]*>','',(meta.get('Artist') or {}).get('value',''))[:140]
            if not license_short or not any(x in license_short.lower() for x in ('cc','public domain','pd-')):continue
            pic=info.get('thumburl') or info.get('url','')
            host=urllib.parse.urlparse(pic).hostname or ''
            if not pic.startswith('https://') or not (host=='upload.wikimedia.org' or host.endswith('.wikimedia.org')):continue
            score=int('poster' in file_title)*3+int(bool(year) and str(year) in file_title)*2
            options.append((score,pic,page.get('title',''),license_short,info.get('descriptionurl',''),artist))
        if not options:raise ValidationError('No confidently matched, reusable Commons poster found. You can add one manually.')
        _,pic,file_title,license_short,source_url,artist=sorted(options,reverse=True)[0]
        req=urllib.request.Request(pic,headers={'User-Agent':'MovieVault/1.0 (personal non-commercial local media catalog)'})
        with urllib.request.urlopen(req,timeout=12) as response:
            mime=response.headers.get_content_type()
            if not mime.startswith('image/'):raise ValidationError('Artwork source returned a non-image')
            raw=response.read(12_000_001)
        if len(raw)>12_000_000:raise ValidationError('Poster exceeds limit')
        self.set_poster(mid,raw,source='Wikimedia Commons',credit=f'{file_title} | Author: {artist or "see source"} | {license_short} | {source_url}')
        return {'provider':'Wikimedia Commons','attribution':file_title,'license':license_short,'source_url':source_url}
    def _tmdb_poster(self,mid,job,replace=False):
        movie=self.movie(mid)
        if movie['poster_locked']:raise ValidationError('Poster locked by user')
        if not replace and movie['poster_path'] and (self.dir/movie['poster_path']).is_file():
            raise ValidationError('Poster already exists. Refresh only unlocked automatic artwork.')
        client=TMDbClient(self.tmdb_credentials.get())
        match,match_method=client.match(movie['display_title'],movie['year'],movie.get('imdb_id',''))
        pic=match.get('poster_path')
        if not pic:raise ValidationError('TMDB matched this film, but has no poster.')
        blob=client.download_poster(pic)
        tmdb_id=match.get('id')
        self.set_poster(mid,blob,source='TMDb',credit=f'TMDb / movie/{tmdb_id} / matched by {match_method}')
        # TMDB images are held in the managed cache, rather than silently copied into
        # permanent user movie directories. The cache is subject to TMDB retention rules.
        return {'provider':'TMDb','tmdb_id':tmdb_id,'method':match_method}
    def expire_tmdb_details(self):
        from datetime import datetime,timezone,timedelta
        cutoff=datetime.now(timezone.utc)-timedelta(days=170)
        with self.connect() as c:
            rows=c.execute("SELECT id,tmdb_metadata_at FROM movies WHERE tmdb_metadata_at<>''").fetchall()
            for r in rows:
                try:date=datetime.fromisoformat(r['tmdb_metadata_at']).astimezone(timezone.utc)
                except (ValueError,TypeError):date=datetime.min.replace(tzinfo=timezone.utc)
                if date<cutoff:
                    c.execute("UPDATE movies SET overview='',cast_names='',tmdb_rating=NULL,tmdb_id=NULL,tmdb_metadata_at='' WHERE id=?",(r['id'],))
    def _refresh_movie_details_impl(self,job,mid):
        movie=self.movie(mid);client=TMDbClient(self.tmdb_credentials.get())
        matched,method=client.match(movie['display_title'],movie['year'],movie['imdb_id'])
        details=client.details(int(matched['id']))
        released=(details.get('release_date') or '')[:4]
        if movie['year'] and released and released!=str(movie['year']) and method!='imdb_id':
            raise ValidationError('TMDB movie year does not match this record')
        cast=[]
        for r in ((details.get('credits') or {}).get('cast') or [])[:20]:
            name=str(r.get('name') or '').strip()
            if name and name not in cast:cast.append(name)
        external=details.get('external_ids') or {}
        ext_imdb=external.get('imdb_id') or details.get('imdb_id') or ''
        if ext_imdb and not re.fullmatch(r'tt\d{5,12}',ext_imdb):ext_imdb=''
        with self.connect() as c:
            locks=set(movie['manual_fields'])
            updates={'tmdb_id':int(matched['id']),'overview':str(details.get('overview') or '')[:3000],
                     'cast_names':', '.join(cast)[:1500], 'tmdb_metadata_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
            rating=details.get('vote_average')
            updates['tmdb_rating']=float(rating) if isinstance(rating,(int,float)) and 0<=rating<=10 else None
            if ext_imdb and 'imdb_id' not in locks and not movie.get('imdb_id'):
                updates['imdb_id']=ext_imdb
            ratingrow=c.execute('SELECT rating FROM imdb_ratings WHERE tconst=?',(ext_imdb or movie.get('imdb_id',''),)).fetchone()
            if ratingrow:updates['imdb_rating']=ratingrow['rating']
            c.execute('UPDATE movies SET '+','.join(k+'=?' for k in updates)+' WHERE id=?',list(updates.values())+[mid])
        job['message']='Movie cast, overview and verified metadata refreshed.'
        return {'movie_id':mid,'cast_count':len(cast),'matched_by':method}
    def refresh_movie_details(self,mid):return self.start_job('movie_details',lambda job:self._refresh_movie_details_impl(job,int(mid)))
    def _online_poster(self,mid,job,replace=False):
        provider=self.settings().get('poster_provider','commons')
        if provider=='none':raise ValidationError('Online poster search is disabled in Settings')
        failures=[]
        if provider=='tmdb':
            try:return self._tmdb_poster(mid,job,replace=replace)
            except (TMDbError,ValidationError,TimeoutError,OSError,urllib.error.URLError) as e:failures.append('TMDb: '+str(e)[:100])
        try:return self._commons_poster(mid,job,replace=replace)
        except (ValidationError,TimeoutError,OSError,urllib.error.URLError) as e:failures.append('Commons: '+str(e)[:100])
        if self.settings().get('auto_frame_fallback')=='1':
            return self._frame_poster_impl(job,mid)
        raise ValidationError('Online artwork unavailable. '+' | '.join(failures)+'. Use Generate Custom Poster if you want a local movie-frame design.')
    def _poster_batch(self,job,limit=10):
        with self.connect() as c:
            mids=[r['id'] for r in c.execute("SELECT id FROM movies WHERE status='available' AND poster_path='' AND poster_locked=0 AND poster_attempted_at='' ORDER BY id DESC LIMIT ?",(limit,))]
        counts={'matched':0,'not_found':0,'attempted':len(mids)};job['total']=len(mids)
        for mid in mids:
            if job.get('cancel'):break
            job['message']=f'Checking reusable artwork for film {job["done"]+1}/{job["total"]}'
            try:self._online_poster(mid,job);counts['matched']+=1
            except (ValidationError,OSError,ValueError,TimeoutError,urllib.error.URLError) as e:
                counts['not_found']+=1;job['message']=str(e)[:120]
            finally:
                with self.connect() as c:c.execute('UPDATE movies SET poster_attempted_at=? WHERE id=?',(time.strftime('%Y-%m-%dT%H:%M:%S%z'),mid))
                job['done']+=1
            time.sleep(.35)
        job['message']=f'Artwork batch completed: {counts["matched"]} found, {counts["not_found"]} unavailable (can be set manually).';return counts
    def fetch_missing_posters(self,limit=10):return self.start_job('poster_batch',lambda j:self._poster_batch(j,min(50,max(1,int(limit)))))
    def fetch_poster(self,mid,replace=False):return self.start_job('poster',lambda j:self._online_poster(mid,j,replace=replace))
    def poster_bytes(self,mid):
        try:r=self.movie(mid)
        except ValidationError:return None
        path=r['poster_path']
        if not path:return None
        p=(self.dir/path).resolve()
        if p.parent!=self.posters.resolve():return None
        try:return p.read_bytes() if p.is_file() else None
        except OSError:return None
    def _enrich_existing_movies(self,job):
        matches=0
        with self.connect() as c:
            # Existing unchanged films are enriched immediately after IMDb import.
            rows=c.execute('SELECT id,display_title,year,manual_fields FROM movies').fetchall()
            for r in rows:
                hit=self._match_imdb(c,r['display_title'],r['year'])
                if not hit:continue
                locks=set(json.loads(r['manual_fields']));vals={k:v for k,v in {'imdb_id':hit['tconst'],'genres':hit['genres'],'year':hit['year']}.items() if k not in locks}
                rating=c.execute('SELECT rating FROM imdb_ratings WHERE tconst=?',(hit['tconst'],)).fetchone()
                if rating:vals['imdb_rating']=rating['rating']
                if vals:
                    c.execute('UPDATE movies SET '+','.join(k+'=?' for k in vals)+' WHERE id=?',list(vals.values())+[r['id']]);matches+=1
        job['message']=f'IMDb imported; {matches} existing movie records enriched.'
        return matches
    def download_imdb(self):
        return self.start_job('imdb_download',self._download_imdb_impl)
    def _download_imdb_impl(self,job):
        # Official non-commercial dataset; no API key and only under explicit user action.
        address='https://datasets.imdbws.com/title.basics.tsv.gz'
        target=self.dir/'title.basics.tsv.gz';part=self.dir/'title.basics.download.partial'
        req=urllib.request.Request(address,headers={'User-Agent':'MovieVault/1.0 personal non-commercial offline catalog'})
        try:
            with urllib.request.urlopen(req,timeout=40) as source,part.open('wb') as output:
                if urllib.parse.urlparse(source.geturl()).scheme!='https':raise ValidationError('IMDb dataset did not use HTTPS')
                declared=int(source.headers.get('Content-Length') or 0)
                if declared>1_200_000_000:raise ValidationError('Unexpectedly large IMDb download')
                job['total']=declared;total=0
                while True:
                    chunk=source.read(1_048_576)
                    if not chunk:break
                    total+=len(chunk)
                    if total>1_200_000_000:raise ValidationError('IMDb dataset download exceeded size limit')
                    output.write(chunk);job['done']=total
                    job['message']=f'Downloading official IMDb dataset: {total//1048576:,} MB received'
            os.replace(part,target)
            job['done']=0;job['total']=0
            return self._imdb_import_impl(job,target)
        finally:
            part.unlink(missing_ok=True)
            # Keep only the searchable SQLite index, not the large compressed input.
            target.unlink(missing_ok=True)
    def _imdb_import_impl(self,job,path):
        p=Path(path).expanduser().resolve()
        if not p.is_file() or not p.name.startswith('title.basics.tsv'):raise ValidationError('Select the official title.basics.tsv or title.basics.tsv.gz file')
        opener=gzip.open if p.suffix=='.gz' else open
        stage=self.dir/'imdb_stage.sqlite'
        try:stage.unlink(missing_ok=True)
        except OSError:raise ValidationError('Previous IMDb import is locked')
        sc=sqlite3.connect(str(stage));count=0
        try:
            sc.execute('CREATE TABLE items(tconst TEXT PRIMARY KEY,title_norm TEXT,primary_title TEXT,year INTEGER,genres TEXT,runtime INTEGER)')
            batch=[]
            with opener(p,'rt',encoding='utf-8',newline='',errors='replace') as stream:
                reader=csv.DictReader(stream,delimiter='\t')
                needed={'tconst','titleType','primaryTitle','startYear','genres'}
                if not reader.fieldnames or not needed.issubset(set(reader.fieldnames)):raise ValidationError('Not an IMDb title.basics dataset')
                for row in reader:
                    if row['titleType'] not in ('movie','tvMovie') or row.get('isAdult')=='1':continue
                    title=row['primaryTitle']; n=normalize(title)
                    if not n:continue
                    year=clean_year(row.get('startYear')); genres=row.get('genres','').replace('\\N','')
                    try:runtime=int(row['runtimeMinutes'])
                    except (ValueError,KeyError,TypeError):runtime=None
                    batch.append((row['tconst'],n,title,year,genres,runtime))
                    if len(batch)>=3000:
                        sc.executemany('INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?)',batch);count+=len(batch);batch=[]
                        job['done']=count;job['message']=f'Imported {count:,} IMDb movie titles…'
                if batch:sc.executemany('INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?)',batch);count+=len(batch)
            sc.commit()
            if count<1:raise ValidationError('No films found in dataset')
            with self.connect() as c:
                c.execute('ATTACH DATABASE ? AS stage',(str(stage),))
                c.execute('DELETE FROM imdb_titles')
                c.execute('INSERT INTO imdb_titles SELECT * FROM stage.items')
                c.commit() # SQLite cannot DETACH an actively written attached database.
                c.execute('DETACH DATABASE stage')
                c.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',('imdb_imported_at',time.strftime('%Y-%m-%dT%H:%M:%S%z')))
            enriched=self._enrich_existing_movies(job)
            return {'titles_imported':count,'existing_movies_enriched':enriched}
        finally:
            sc.close()
            try:stage.unlink(missing_ok=True)
            except OSError:pass
    def _imdb_ratings_import_impl(self,job,path):
        src=Path(path).expanduser().resolve()
        if not src.is_file() or not src.name.startswith('title.ratings.tsv') or src.stat().st_size>500_000_000:
            raise ValidationError('Select an official title.ratings.tsv.gz file')
        stage=self.dir/'imdb_ratings_stage.sqlite'
        if stage.exists():raise ValidationError('Another ratings import is staged')
        stage_db=sqlite3.connect(str(stage));counter=0
        try:
            stage_db.execute('CREATE TABLE ratings(tconst TEXT PRIMARY KEY,rating REAL,votes INTEGER)')
            opener=gzip.open if src.suffix=='.gz' else open
            with opener(src,'rt',encoding='utf8',newline='',errors='replace') as source:
                reader=csv.DictReader(source,delimiter='\t')
                if not reader.fieldnames or not {'tconst','averageRating','numVotes'}.issubset(reader.fieldnames):raise ValidationError('Invalid IMDb ratings dataset')
                batch=[]
                for r in reader:
                    if not re.fullmatch(r'tt\d{5,12}',r['tconst']):continue
                    try:rating=float(r['averageRating']);votes=int(r['numVotes'])
                    except (ValueError,TypeError):continue
                    if not 0<=rating<=10 or votes<0:continue
                    batch.append((r['tconst'],rating,votes))
                    if len(batch)>=4000:
                        stage_db.executemany('INSERT OR REPLACE INTO ratings VALUES(?,?,?)',batch)
                        counter+=len(batch);batch=[];job['done']=counter;job['message']=f'Indexed {counter:,} IMDb ratings…'
                if batch:stage_db.executemany('INSERT OR REPLACE INTO ratings VALUES(?,?,?)',batch);counter+=len(batch)
            if not counter:raise ValidationError('No valid IMDb ratings found')
            stage_db.commit();stage_db.close();stage_db=None
            with self.connect() as c:
                c.execute('ATTACH DATABASE ? AS incoming',(str(stage),))
                c.execute('DELETE FROM imdb_ratings')
                c.execute('INSERT INTO imdb_ratings SELECT * FROM incoming.ratings')
                c.commit();c.execute('DETACH DATABASE incoming')
                c.execute('UPDATE movies SET imdb_rating=(SELECT r.rating FROM imdb_ratings r WHERE r.tconst=movies.imdb_id) WHERE imdb_id IN (SELECT tconst FROM imdb_ratings)')
                c.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',('imdb_ratings_at',time.strftime('%Y-%m-%dT%H:%M:%S%z')))
            return {'ratings_indexed':counter}
        finally:
            if stage_db:stage_db.close()
            stage.unlink(missing_ok=True)
    def import_imdb_ratings(self,path):return self.start_job('imdb_ratings_import',lambda job:self._imdb_ratings_import_impl(job,path))
    def _download_imdb_ratings_impl(self,job):
        address='https://datasets.imdbws.com/title.ratings.tsv.gz';target=self.dir/'title.ratings.tsv.gz';part=self.dir/'title.ratings.partial'
        try:
            req=urllib.request.Request(address,headers={'User-Agent':'MovieVault/2 personal non-commercial local catalog'})
            with urllib.request.urlopen(req,timeout=40) as src,part.open('wb') as out:
                if urllib.parse.urlsplit(src.geturl()).scheme!='https':raise ValidationError('Ratings dataset must download over HTTPS')
                size=0
                while True:
                    chunk=src.read(1048576)
                    if not chunk:break
                    size+=len(chunk)
                    if size>500_000_000:raise ValidationError('Ratings dataset exceeded size limit')
                    out.write(chunk);job['done']=size;job['message']=f'Downloaded {size//1048576} MB of IMDb ratings'
            os.replace(part,target);job['done']=0
            return self._imdb_ratings_import_impl(job,target)
        finally:part.unlink(missing_ok=True);target.unlink(missing_ok=True)
    def download_imdb_ratings(self):return self.start_job('imdb_ratings_download',self._download_imdb_ratings_impl)
    def import_imdb(self,path):return self.start_job('imdb_import',lambda j:self._imdb_import_impl(j,path))
    def match_imdb(self,mid):
        movie=self.movie(mid)
        with self.connect() as c:
            hit=self._match_imdb(c,movie['display_title'],movie['year'])
            if not hit:return {'matched':False}
            locks=set(movie['manual_fields']);updates={}
            for k,v in {'genres':hit['genres'],'imdb_id':hit['tconst'],'year':hit['year']}.items():
                if k not in locks:updates[k]=v
            rating=c.execute('SELECT rating FROM imdb_ratings WHERE tconst=?',(hit['tconst'],)).fetchone()
            if rating:updates['imdb_rating']=rating['rating']
            if updates:c.execute('UPDATE movies SET '+','.join(k+'=?' for k in updates)+' WHERE id=?',list(updates.values())+[mid])
            return {'matched':True,'imdb_id':hit['tconst'],'updates':updates}
    def backup(self,target=None):
        dst=Path(target).expanduser().resolve() if target else self.backups/('MovieVault_Backup_'+time.strftime('%Y%m%d_%H%M%S')+'.zip')
        if dst.suffix.lower()!='.zip':raise ValidationError('Backup must have .zip extension')
        if not dst.parent.is_dir():raise ValidationError('Backup destination folder does not exist')
        if dst.exists():raise ValidationError('Backup already exists; no overwrite performed')
        with tempfile.TemporaryDirectory() as td:
            snap=Path(td)/'movievault.sqlite'
            with self.connect() as c:
                out=sqlite3.connect(str(snap))
                try:c.backup(out)
                finally:out.close()
            temp=dst.with_name(dst.name+'.partial')
            try:
                with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                    z.write(snap,'movievault.sqlite')
                    manifest={'product':'MovieVault','version':VERSION,'schema':SCHEMA_VERSION,'created':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
                    z.writestr('manifest.json',json.dumps(manifest))
                    with self.connect() as dbcon:
                        tmdb_ids={r['id'] for r in dbcon.execute("SELECT id FROM movies WHERE poster_source='TMDb'")}
                    for f in self.posters.glob('*.jpg'):
                        # TMDB licensed artwork is a time-limited cache, not permanent portable content.
                        if f.stem.isdigit() and int(f.stem) in tmdb_ids:continue
                        if f.is_file() and not f.is_symlink() and re.fullmatch(r'\d+\.jpg',f.name):z.write(f,'posters/'+f.name)
                os.replace(temp,dst)
            finally:temp.unlink(missing_ok=True)
        return str(dst)
    def validate_backup(self,path):
        src=Path(path).expanduser().resolve()
        if not src.is_file() or src.is_symlink():raise ValidationError('Backup file not found')
        if src.stat().st_size>BACKUP_MAX_ARCHIVE_BYTES:raise ValidationError('Backup archive exceeds safety limit')
        try:
            with zipfile.ZipFile(src) as z:
                files=z.infolist();names=[f.filename for f in files];name_set=set(names)
                if len(names)!=len(name_set):raise ValidationError('Backup contains duplicate archive members')
                if 'manifest.json' not in name_set or 'movievault.sqlite' not in name_set:raise ValidationError('Not a MovieVault backup')
                if len(files)>50000 or sum(f.file_size for f in files)>BACKUP_MAX_UNCOMPRESSED_BYTES:raise ValidationError('Backup exceeds safety limit')
                for info in files:
                    if info.filename not in ('manifest.json','movievault.sqlite') and not re.fullmatch(r'posters/\d+\.jpg',info.filename):raise ValidationError('Unexpected archive member')
                    if info.is_dir() or ((info.external_attr >> 16)&0o170000)==0o120000:raise ValidationError('Unsafe backup member')
                    if info.filename=='movievault.sqlite' and info.file_size>BACKUP_MAX_DATABASE_BYTES:raise ValidationError('Database exceeds backup safety limit')
                    if info.filename.startswith('posters/') and info.file_size>BACKUP_MAX_POSTER_BYTES:raise ValidationError('Poster exceeds backup safety limit')
                    if info.compress_size and info.file_size>10_000_000 and info.file_size/max(1,info.compress_size)>400:
                        raise ValidationError('Suspicious ZIP compression ratio')
                manifest_info=z.getinfo('manifest.json')
                if manifest_info.file_size>1_000_000:raise ValidationError('Backup manifest exceeds safety limit')
                manifest=json.loads(z.read(manifest_info))
                schema=int(manifest.get('schema',999))
                if manifest.get('product')!='MovieVault' or not 1<=schema<=SCHEMA_VERSION:
                    raise ValidationError('Unsupported or newer backup version')
                if z.testzip() is not None:raise ValidationError('Backup failed CRC validation')
                with tempfile.TemporaryDirectory(prefix='mv-backup-validate-') as td:
                    candidate=Path(td)/'movievault.sqlite'
                    with z.open('movievault.sqlite') as source,candidate.open('wb') as destination:
                        copied=_copy_limited(source,destination,BACKUP_MAX_DATABASE_BYTES)
                    if copied!=z.getinfo('movievault.sqlite').file_size:raise ValidationError('Backup database size is inconsistent')
                    _validate_restore_database(candidate,schema)
        except ValidationError:raise
        except (zipfile.BadZipFile,zipfile.LargeZipFile,RuntimeError,ValueError,TypeError,KeyError,OSError) as exc:
            raise ValidationError('Backup archive is corrupt or unreadable') from exc
        return {'source':str(src),'manifest':manifest}
    def stage_restore(self,path):
        src=Path(path).expanduser().resolve();dest=self.dir/'restore_pending.zip';part=self.dir/'restore_pending.partial'
        if not src.is_file() or src.is_symlink():raise ValidationError('Backup file not found')
        part.unlink(missing_ok=True)
        try:
            with src.open('rb') as source,part.open('wb') as destination:
                _copy_limited(source,destination,BACKUP_MAX_ARCHIVE_BYTES)
            # Validate the exact private copy that will be activated, closing the
            # source-to-stage race and keeping invalid data out of restore_pending.
            self.validate_backup(part)
            os.replace(part,dest)
        finally:part.unlink(missing_ok=True)
        return 'Backup fully validated and staged. Restart MovieVault to restore; a safety backup is created first.'
    def _extract_restore_archive(self,pending:Path,destination:Path,manifest:dict):
        with zipfile.ZipFile(pending) as z:
            database=destination/'movievault.sqlite'
            with z.open('movievault.sqlite') as source,database.open('wb') as output:
                copied=_copy_limited(source,output,BACKUP_MAX_DATABASE_BYTES)
            if copied!=z.getinfo('movievault.sqlite').file_size:raise ValidationError('Backup database size is inconsistent')
            for info in z.infolist():
                if not re.fullmatch(r'posters/\d+\.jpg',info.filename):continue
                target=destination/info.filename;target.parent.mkdir(exist_ok=True)
                with z.open(info) as source,target.open('wb') as output:
                    copied=_copy_limited(source,output,BACKUP_MAX_POSTER_BYTES)
                if copied!=info.file_size:raise ValidationError('Backup poster size is inconsistent')
        _validate_restore_database(database,int(manifest['schema']))
        return database
    def _activate_restore_archive(self,pending:Path,manifest:dict):
        with tempfile.TemporaryDirectory(prefix='mv-restore-',dir=self.dir) as td:
            staged=Path(td)/'staged';staged.mkdir()
            candidate=self._extract_restore_archive(pending,staged,manifest)
            rollback=Path(td)/'live_before_restore.sqlite'
            with self.connect() as current:
                snapshot=sqlite3.connect(str(rollback))
                try:current.backup(snapshot)
                finally:snapshot.close()
            old_posters=self.dir/('posters_before_restore_'+str(time.time_ns()))
            try:
                for suffix in ('-wal','-shm'):(self.dir/('movievault.sqlite'+suffix)).unlink(missing_ok=True)
                os.replace(candidate,self.db)
                if (staged/'posters').exists():
                    if self.posters.exists():os.replace(self.posters,old_posters)
                    os.replace(staged/'posters',self.posters)
            except Exception:
                for suffix in ('-wal','-shm'):(self.dir/('movievault.sqlite'+suffix)).unlink(missing_ok=True)
                # The rollback snapshot is a complete SQLite backup of the live
                # catalog taken immediately before activation.
                os.replace(rollback,self.db)
                if old_posters.exists():
                    if self.posters.exists():shutil.rmtree(self.posters,ignore_errors=True)
                    os.replace(old_posters,self.posters)
                raise
            finally:
                if old_posters.exists():shutil.rmtree(old_posters,ignore_errors=True)
    def _quarantine_failed_restore(self,pending:Path,failure:Exception) -> bool:
        quarantined=False
        try:
            folder=self.dir/'restore_quarantine';folder.mkdir(exist_ok=True)
            target=folder/('restore_failed_'+time.strftime('%Y%m%d_%H%M%S')+'_'+str(time.time_ns())+'.zip')
            os.replace(pending,target);quarantined=True
        except OSError:
            # Even if quarantine is unavailable, never let the pending restore
            # prevent normal startup. It will be retried safely on a later launch.
            quarantined=False
        try:self.diagnostics.event('restore_activation_recovered',failure_type=type(failure).__name__,quarantined=quarantined)
        except OSError:pass
        return quarantined
    def process_pending_restore(self):
        pending=self.dir/'restore_pending.zip'
        if not pending.exists():return
        try:
            info=self.validate_backup(pending)
            safety=self.backups/('Before_Restore_'+time.strftime('%Y%m%d_%H%M%S')+'.zip')
            if safety.exists():safety=safety.with_name(safety.stem+'_'+str(time.time_ns())+'.zip')
            self.backup(safety)
            self._activate_restore_archive(pending,info['manifest'])
        except Exception as failure:
            self._quarantine_failed_restore(pending,failure)
            return False
        pending.unlink(missing_ok=True)
        try:self.diagnostics.event('restore_activated')
        except OSError:pass
        return True

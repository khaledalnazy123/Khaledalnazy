"""Privacy-first structured activity log and user-triggered support ZIP.

Never record request bodies, tokens, email addresses, home paths, subtitles or movie
filenames. The support package does not contain the live DB or credential files.
"""
from __future__ import annotations
import json,os,platform,re,threading,time,sys,zipfile
from pathlib import Path

MAX_LOG=2_000_000
LOG_COUNT=5
SENSITIVE_KEYS={'token','read_token','api_key','authorization','password','secret','credential'}

def _safe(value):
    if isinstance(value,(int,float,bool)) or value is None:return value
    text=str(value)[:350]
    text=re.sub(r'(?i)bearer\s+\S+','[REDACTED AUTH]',text)
    text=re.sub(r'AIza[A-Za-z0-9_-]{20,}','[REDACTED GEMINI KEY]',text)
    text=re.sub(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])','[REDACTED JWT]',text)
    text=re.sub(r'(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+',r'\1=[REDACTED]',text)
    text=re.sub(r'(?i)[A-Z]:[\\/][^,\r\n\t;<>|]*','[REDACTED PATH]',text)
    text=re.sub(r'\\\\[^\\/\s]+[\\/][^,\r\n\t;<>|]+','[REDACTED UNC PATH]',text)
    text=re.sub(r'(?<![A-Za-z0-9])/(?:home|Users|Volumes|mnt|media|private|tmp|var|opt|Library|Applications)/[^,\r\n\t;<>|]*','[REDACTED PATH]',text)
    text=re.sub(r'(?i)[^,\r\n\t/\\;<>|]*\.(?:mkv|mp4|avi|mov|wmv|m4v|ts|srt|ass|ssa|vtt|sub)(?![A-Za-z0-9])','[REDACTED FILENAME]',text)
    text=re.sub(r'(?i)(?<![A-Z0-9._%+\-])[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}(?![A-Z0-9._%+\-])','[REDACTED EMAIL]',text)
    return text

class Diagnostics:
    def __init__(self,data_dir):
        self.folder=Path(data_dir)/'logs';self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'events.jsonl';self._lock=threading.Lock()
    def event(self,name,**fields):
        # Opt-in names and safe scalar metadata only, never arbitrary request payloads.
        data={'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'event':_safe(name)}
        for k,v in fields.items():
            if k.lower() in SENSITIVE_KEYS:continue
            if not re.fullmatch(r'[a-z_]{1,35}',k):continue
            data[k]=_safe(v)
        line=json.dumps(data,ensure_ascii=False)+'\n'
        with self._lock:
            if self.path.exists() and self.path.stat().st_size+len(line.encode())>MAX_LOG:
                for n in range(LOG_COUNT-1,0,-1):
                    src=self.folder/f'events.{n}.jsonl';dest=self.folder/f'events.{n+1}.jsonl'
                    if src.is_file():os.replace(src,dest)
                os.replace(self.path,self.folder/'events.1.jsonl')
            with self.path.open('a',encoding='utf8') as f:f.write(line)
    def export(self,catalog):
        self.event('diagnostic_export_requested')
        dst=catalog.backups/('MovieVault_Diagnostics_'+time.strftime('%Y%m%d_%H%M%S')+'.zip')
        if dst.exists():dst=dst.with_name(dst.stem+'_'+str(time.time_ns())+'.zip')
        with catalog.connect() as c:
            counts={t:int(c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]) for t in ('roots','movies','subtitles','imdb_titles')}
            integrity=c.execute('PRAGMA quick_check').fetchone()[0]
        metadata={'app_version':getattr(sys.modules.get('mv_core'),'VERSION','development'),
                  'platform':platform.system(),'platform_release':platform.release(),
                  'python':platform.python_version(),'sqlite_integrity':integrity,
                  'catalog_counts':counts, 'credentials_included':False,
                  'privacy':'No raw database, private paths, movie filenames, or API tokens included.'}
        partial=dst.with_suffix('.partial')
        try:
            with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('diagnostics.json',json.dumps(metadata,indent=2,ensure_ascii=False))
                for f in [self.folder/'events.jsonl']+[self.folder/f'events.{n}.jsonl' for n in range(1,LOG_COUNT+1)]:
                    if f.is_file() and f.stat().st_size<=MAX_LOG:
                        z.writestr('logs/'+f.name,''.join(_safe(line)+'\n' for line in f.read_text(encoding='utf8',errors='replace').splitlines()))
                z.writestr('README.txt','MovieVault privacy-minimized diagnostic archive. Review before sharing. No credentials, raw library database, filenames or user paths are included.\n')
            os.replace(partial,dst)
        finally:partial.unlink(missing_ok=True)
        return str(dst)

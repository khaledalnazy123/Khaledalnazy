"""TMDB read-only client and per-user credential storage (never in SQLite or backups)."""
from __future__ import annotations
import ctypes, io, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from ctypes import wintypes

class TMDbError(ValueError): pass

class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]

def _blob(data:bytes):
    buffer = ctypes.create_string_buffer(data)
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

def _protect(raw:bytes, decrypt=False):
    if sys.platform != 'win32':
        raise TMDbError('Persistent TMDB credentials require Windows DPAPI.')
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kern=ctypes.WinDLL('kernel32',use_last_error=True)
    crypt.CryptProtectData.argtypes=[ctypes.POINTER(_Blob),ctypes.c_wchar_p,ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    crypt.CryptProtectData.restype=wintypes.BOOL
    crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(_Blob),ctypes.POINTER(ctypes.c_wchar_p),ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    crypt.CryptUnprotectData.restype=wintypes.BOOL
    kern.LocalFree.argtypes=[ctypes.c_void_p];kern.LocalFree.restype=ctypes.c_void_p
    blob, backing=_blob(raw); out=_Blob()
    func=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    # CRYPTPROTECT_UI_FORBIDDEN: no unexpected desktop prompts.
    if decrypt: ok=func(ctypes.byref(blob),None,None,None,None,1,ctypes.byref(out))
    else: ok=func(ctypes.byref(blob),'MovieVault TMDB token',None,None,None,1,ctypes.byref(out))
    if not ok:raise TMDbError('Cannot protect/read TMDB credential with current Windows user account')
    try:return ctypes.string_at(out.pbData,out.cbData)
    finally:kern.LocalFree(ctypes.cast(out.pbData,ctypes.c_void_p))

class CredentialStore:
    def __init__(self,root):self.path=Path(root)/'tmdb_credential.dpapi';self._session=None
    def get(self):
        if self._session:return self._session
        if not self.path.is_file():return ''
        try:return _protect(self.path.read_bytes(),decrypt=True).decode('ascii')
        except (OSError,UnicodeError,TMDbError):return ''
    def save(self,token):
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9._~-]{25,2048}',token):raise TMDbError('Invalid TMDB read access token')
        if sys.platform != 'win32':
            self._session=token # development mode: memory only; never write cleartext
            return
        protected=_protect(token.encode('ascii'))
        tmp=self.path.with_suffix('.partial')
        try:
            with tmp.open('wb') as f:f.write(protected)
            os.replace(tmp,self.path)
        finally:tmp.unlink(missing_ok=True)
        self._session=token
    def clear(self):
        self._session=None
        self.path.unlink(missing_ok=True)

class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        a,b=urllib.parse.urlsplit(req.full_url),urllib.parse.urlsplit(newurl)
        if b.scheme!='https' or b.hostname!=a.hostname:raise TMDbError('Unexpected cross-host redirect refused')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_trusted(req,timeout):
    # Never forward the Bearer credential to a different host on redirects.
    return urllib.request.build_opener(_SameHostRedirect()).open(req,timeout=timeout)

class TMDbClient:
    API='https://api.themoviedb.org/3'
    IMAGE='https://image.tmdb.org/t/p/w500'
    def __init__(self,token):
        if not token:raise TMDbError('Connect TMDB in Settings first')
        self.token=token
    def get(self,endpoint,params=None):
        # Endpoint is hard-coded at each call site; user input goes in URL-encoded params only.
        if not endpoint.startswith('/') or '://' in endpoint or '?' in endpoint or '..' in endpoint:raise TMDbError('Invalid TMDB request')
        url=self.API+endpoint+('?' + urllib.parse.urlencode(params) if params else '')
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+self.token,'Accept':'application/json','User-Agent':'MovieVault/1.0 personal movie archive'})
        try:
            with open_trusted(req,timeout=12) as response:
                raw=response.read(1_500_001)
                if len(raw)>1_500_000:raise TMDbError('TMDB response exceeded limit')
                data=json.loads(raw)
                if not isinstance(data,dict):raise TMDbError('Unexpected TMDB response')
                return data
        except urllib.error.HTTPError as e:
            if e.code in (401,403):raise TMDbError('TMDB access denied. Check API Read Access Token.') from None
            if e.code==429:raise TMDbError('TMDB rate limit reached. Try again later.') from None
            raise TMDbError(f'TMDB returned HTTP {e.code}') from None
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as e:
            raise TMDbError('TMDB connection failed or invalid response') from e
    def test_connection(self):
        data=self.get('/configuration')
        if not isinstance(data,dict) or 'images' not in data:raise TMDbError('Unexpected TMDB configuration response')
        return True
    def match(self,title,year=None,imdb_id=''):
        from mv_core import normalize
        if re.fullmatch(r'tt\d{5,12}',imdb_id or ''):
            found=self.get('/find/'+imdb_id,{'external_source':'imdb_id'})
            candidates=found.get('movie_results') or []
            if len(candidates)==1:return candidates[0], 'imdb_id'
            if len(candidates)>1:raise TMDbError('IMDb ID returned several movie results; select manually')
        params={'query':title,'include_adult':'false','language':'en-US'}
        if year:params['year']=str(year)
        found=self.get('/search/movie',params)
        candidates=[]
        for entry in found.get('results') or []:
            if normalize(entry.get('title','')) != normalize(title) and normalize(entry.get('original_title','')) != normalize(title):continue
            release=entry.get('release_date','')
            if year and (len(release)<4 or release[:4]!=str(year)):continue
            candidates.append(entry)
        # Never guess from popularity or choose among indistinguishable candidates.
        if len(candidates)!=1:raise TMDbError('No unique exact TMDB movie match. Check title/year or IMDb ID.')
        return candidates[0], 'title_year'
    def details(self,tmdb_id:int):
        if not isinstance(tmdb_id,int) or not 1<=tmdb_id<=100_000_000:raise TMDbError('Invalid TMDB film identifier')
        data=self.get(f'/movie/{tmdb_id}',{'append_to_response':'credits,external_ids','language':'en-US'})
        if int(data.get('id') or -1)!=tmdb_id:raise TMDbError('TMDB returned mismatched movie details')
        return data
    def download_poster(self,poster_path):
        if not isinstance(poster_path,str) or not re.fullmatch(r'/[a-zA-Z0-9_/-]{1,120}\.(?:jpg|jpeg|png|webp)',poster_path):raise TMDbError('Invalid TMDB poster path')
        req=urllib.request.Request(self.IMAGE+poster_path,headers={'User-Agent':'MovieVault/1.0 personal movie archive','Accept':'image/jpeg,image/png,image/webp'})
        try:
            with open_trusted(req,timeout=18) as resp:
                if not resp.headers.get_content_type().startswith('image/'):raise TMDbError('Poster response is not an image')
                blob=resp.read(12_000_001)
            if len(blob)>12_000_000:raise TMDbError('Poster image too large')
            if len(blob)<100:raise TMDbError('Poster image is empty')
            return blob
        except (urllib.error.URLError,OSError,TimeoutError) as e:raise TMDbError('TMDB poster download failed') from e

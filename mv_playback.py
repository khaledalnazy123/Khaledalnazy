"""Non-destructive playback and explicit external subtitle selection.

No movie/real subtitle file is renamed, replaced or deleted, even transiently.
"""
from __future__ import annotations
import os,re,shutil,subprocess,sys
from pathlib import Path

class PlaybackError(ValueError):pass
class SubtitleChoiceRequired(PlaybackError):pass


def _verified_external(movie:dict, subtitle_id:int) ->Path:
    sub=next((s for s in movie.get('subtitles',[]) if int(s['id'])==int(subtitle_id)),None)
    if not sub:raise PlaybackError('The requested subtitle does not belong to this movie.')
    if sub['kind']!='external':raise PlaybackError('An embedded subtitle track must be selected in the video player itself.')
    if Path(sub['filename']).name!=sub['filename'] or not re.fullmatch(r'[^\\/\x00-\x1f]{1,260}',sub['filename']):
        raise PlaybackError('Unsafe subtitle filename.')
    moviepath=Path(movie['path']);candidate=moviepath.parent/sub['filename']
    if candidate.is_symlink() or not candidate.is_file() or candidate.resolve().parent!=moviepath.parent.resolve():
        raise PlaybackError('The selected external subtitle is missing or unsafe.')
    if candidate.suffix.lower() not in ('.srt','.sub','.idx','.ass','.ssa','.sup','.vtt','.smi','.ttml','.pgs'):
        raise PlaybackError('Unsupported subtitle file type.')
    return candidate


def playback_plan(movie:dict, *, subtitle_id=None, no_subtitles=False):
    video=Path(movie['path'])
    if movie.get('status')!='available' or not video.is_file() or video.is_symlink():
        raise PlaybackError('The movie is not currently available on disk.')
    if no_subtitles:return {'video':str(video),'subtitle':None,'mute_subtitles':True}
    prefs=movie.get('playback_preference') or 'auto'
    if subtitle_id is not None:return {'video':str(video),'subtitle':str(_verified_external(movie,int(subtitle_id))),'mute_subtitles':False}
    if prefs=='none':return {'video':str(video),'subtitle':None,'mute_subtitles':True}
    if prefs=='ask':raise SubtitleChoiceRequired('Select a subtitle before playback.')
    if prefs=='selected':
        mid=movie.get('preferred_subtitle_id')
        if mid is None:raise SubtitleChoiceRequired('Your preferred subtitle was removed. Choose another subtitle.')
        return {'video':str(video),'subtitle':str(_verified_external(movie,int(mid))),'mute_subtitles':False}
    external=[s for s in movie.get('subtitles',[]) if s.get('kind')=='external']
    if len(external)>1:raise SubtitleChoiceRequired('Several external subtitles are available. Choose which one to play.')
    if len(external)==1:
        return {'video':str(video),'subtitle':str(_verified_external(movie,external[0]['id'])),'mute_subtitles':False}
    # Embedded streams are interpreted by the player's own stream selector.
    return {'video':str(video),'subtitle':None,'mute_subtitles':False}


def find_player():
    mpv=shutil.which('mpv') or shutil.which('mpv.exe')
    if mpv:return 'mpv',mpv
    vlc=shutil.which('vlc') or shutil.which('vlc.exe')
    if vlc:return 'vlc',vlc
    if sys.platform=='win32':
        for var in ('PROGRAMFILES','PROGRAMFILES(X86)'):
            root=os.environ.get(var)
            if root:
                for prog,rel in [('vlc','VideoLAN/VLC/vlc.exe'),('mpv','mpv/mpv.exe')]:
                    candidate=Path(root)/rel
                    if candidate.is_file():return prog,str(candidate)
    return None,None


def launch_playback(plan, native_launch=None):
    prog,exe=find_player()
    if not prog:
        if plan['subtitle'] or plan['mute_subtitles']:
            raise PlaybackError('To select/disable subtitles without renaming any files, install VLC or mpv. Their subtitles are passed by command-line arguments.')
        if native_launch is None:raise PlaybackError('System video launcher not available.')
        native_launch(plan['video']);return {'player':'Windows default','subtitle_loaded':False}
    if prog=='mpv':
        cmd=[exe,'--force-window=yes']
        if plan['mute_subtitles']:cmd.append('--sid=no')
        elif plan['subtitle']:cmd.append('--sub-file='+plan['subtitle'])
        cmd.append(plan['video'])
    else:
        cmd=[exe,'--started-from-file']
        if plan['mute_subtitles']:cmd.append('--no-sub-autodetect-file')
        elif plan['subtitle']:cmd.append('--sub-file='+plan['subtitle'])
        cmd.append(plan['video'])
    subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=(subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
    return {'player':prog,'subtitle_loaded':bool(plan['subtitle'])}

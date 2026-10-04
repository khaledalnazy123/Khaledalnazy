"""MovieVault Windows entry point (pythonw / PyInstaller --windowed, no console)."""
import sys,traceback
from pathlib import Path
from mv_server import run_app
from mv_core import Catalog,default_data_dir
if __name__=='__main__':
    try:
        if '--backup-only' in sys.argv:
            cat=Catalog()
            cat.backup()
        else:
            run_app()
    except Exception as exc:
        log=default_data_dir()/'startup_error.log'
        try:
            log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('a',encoding='utf-8') as out:
                out.write('\nMovieVault failed to start:\n'+traceback.format_exc()+'\n')
        except OSError:log=Path('startup_error.log')
        if '--backup-only' not in sys.argv and sys.platform=='win32':
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None,f'MovieVault could not start.\nDetails saved to:\n{log}\n\n{str(exc)[:250]}','MovieVault Startup Error',0x10)
            except Exception:pass
        sys.exit(1)

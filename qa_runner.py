from __future__ import annotations
import json, os, platform, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPORT_DIR=ROOT/'qa_reports'
REPORT_DIR.mkdir(exist_ok=True)
STAMP=time.strftime('%Y%m%d_%H%M%S')

def run(name, cmd, timeout=180):
    started=time.time()
    try:
        p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
        return {
            'name':name,'command':' '.join(cmd),'returncode':p.returncode,
            'seconds':round(time.time()-started,3),'stdout':p.stdout[-30000:],'stderr':p.stderr[-30000:]
        }
    except subprocess.TimeoutExpired as e:
        return {'name':name,'command':' '.join(cmd),'returncode':124,'seconds':round(time.time()-started,3),
                'stdout':(e.stdout or '')[-30000:] if isinstance(e.stdout,str) else '',
                'stderr':((e.stderr or '')[-30000:] if isinstance(e.stderr,str) else '')+'\nTIMEOUT'}
    except Exception as e:
        return {'name':name,'command':' '.join(cmd),'returncode':125,'seconds':round(time.time()-started,3),'stdout':'','stderr':repr(e)}

def main():
    py=sys.executable
    steps=[
        ('Unit + integration regression tests',[py,'-m','unittest','discover','-s','tests','-q'],240),
        ('Python syntax compile',[py,'-m','compileall','-q','mv_core.py','mv_diagnostics.py','mv_gemini.py','mv_migration.py','mv_playback.py','mv_server.py','mv_tmdb.py','MovieVault.pyw','dev.py','tests'],180),
    ]
    try:
        import playwright  # noqa
        steps.append(('Visual browser smoke test',[py,'tests/visual_smoke.py'],240))
    except Exception:
        pass
    results=[run(n,c,t) for n,c,t in steps]
    passed=all(r['returncode']==0 for r in results)
    payload={
        'product':'MovieVault','suite':'Automated QA','created':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'platform':platform.platform(),'python':sys.version.split()[0],
        'passed':passed,'results':results,
        'note':'This automated suite does not replace real Windows acceptance testing for WebView2, DPAPI, external API credentials, VLC/mpv and Setup.exe.'
    }
    jpath=REPORT_DIR/f'QA_{STAMP}.json';tpath=REPORT_DIR/f'QA_{STAMP}.txt'
    jpath.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf8')
    lines=[f"MovieVault Automated QA - {'PASS' if passed else 'FAIL'}",payload['created'],payload['platform'],f"Python {payload['python']}",'']
    for r in results:
        lines += [f"[{ 'PASS' if r['returncode']==0 else 'FAIL' }] {r['name']} ({r['seconds']}s)",f"  {r['command']}"]
        if r['stderr'].strip(): lines += ['  STDERR:',r['stderr'].strip()]
        if r['stdout'].strip(): lines += ['  STDOUT:',r['stdout'].strip()]
        lines.append('')
    lines += [payload['note'],f'JSON report: {jpath.name}']
    tpath.write_text('\n'.join(lines),encoding='utf8')
    print('\n'.join(lines))
    print(f'\nReports saved to: {REPORT_DIR}')
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())

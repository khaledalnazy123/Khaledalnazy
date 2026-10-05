"""Reproducible synthetic P2A scale benchmark; no real video payloads are created."""
from __future__ import annotations
import json,os,statistics,tempfile,time
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from mv_core import Catalog

BUDGETS={
    # These gates leave substantial margin above the Linux reference timings
    # while still detecting a return to per-file directory scans or other
    # order-of-magnitude regressions.
    1_000:{'startup':0.5,'list':0.5,'filter':0.5,'stats':0.5,'unchanged_scan':3.0},
    10_000:{'startup':1.0,'list':1.0,'filter':1.0,'stats':1.0,'unchanged_scan':20.0},
}

def _measure(fn,repeats=3):
    values=[]
    for _ in range(repeats):
        started=time.perf_counter();fn();values.append(time.perf_counter()-started)
    return statistics.median(values)

def run_benchmark(movie_count:int) -> dict:
    if movie_count not in BUDGETS:raise ValueError('Benchmark size must be 1000 or 10000')
    with tempfile.TemporaryDirectory(prefix=f'mv-p2a-{movie_count}-') as folder:
        base=Path(folder);data=base/'data';root=base/'synthetic-library';catalog=Catalog(data)
        catalog.set_settings({'auto_posters':'0','poster_in_folder':'0','auto_imdb':'0'})
        names=[f'Movie {i:05d} (2020) [1080p] [YTS].mkv' for i in range(movie_count)]
        with catalog.connect() as db:
            root_id=db.execute('INSERT INTO roots(path) VALUES(?)',(str(root),)).lastrowid
            rows=[]
            for i,name in enumerate(names):
                group=('YTS' if i%4==0 else 'QXR' if i%4==1 else 'YTSMX' if i%4==2 else '')
                rows.append((root_id,name,name,name,f'Movie {i:05d}',2020,'Drama',group,'1080p',1,1000,'{}','sampled','full-digest','available','2026','2026',123,'[]'))
            db.executemany('''INSERT INTO movies(root_id,relative_path,original_filename,current_filename,display_title,year,genres,release_group,
                resolution_tag,resolution_verified,size_bytes,raw_probe,fingerprint,content_sha256,status,added_at,last_seen,modified_ns,manual_fields)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',rows)
        started=time.perf_counter();catalog=Catalog(data);startup=time.perf_counter()-started
        listing=lambda:catalog.movies(page=1,limit=150,sort='title')
        filtering=lambda:catalog.movies(release_group='yts',quality='1080p',year_from=2020,year_to=2020,page=1,limit=150)
        measurements={'startup':startup,'list':_measure(listing),'filter':_measure(filtering),'stats':_measure(catalog.stats)}
        real_is_dir=Path.is_dir;real_is_symlink=Path.is_symlink;real_stat=Path.stat
        def fake_is_dir(path):return True if path==root else real_is_dir(path)
        def fake_is_symlink(path):return False if path.parent==root else real_is_symlink(path)
        def fake_stat(path):
            if path.parent==root and path.suffix=='.mkv':return SimpleNamespace(st_size=1000,st_mtime_ns=123)
            return real_stat(path)
        job={'cancel':False,'total':0,'done':0,'message':''}
        started=time.perf_counter()
        with patch('mv_core.os.walk',return_value=[(str(root),[],names)]),patch.object(Path,'is_dir',fake_is_dir),patch.object(Path,'is_symlink',fake_is_symlink),patch.object(Path,'stat',fake_stat):
            result=catalog._scan_impl(job,[root_id])
        measurements['unchanged_scan']=time.perf_counter()-started
        if result['unchanged']!=movie_count:raise AssertionError(f'Expected {movie_count} unchanged movies, got {result}')
        return {'movies':movie_count,'measurements':{key:round(value,6) for key,value in measurements.items()},'budgets':BUDGETS[movie_count]}

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('movies',type=int,choices=sorted(BUDGETS));args=parser.parse_args()
    result=run_benchmark(args.movies);print(json.dumps(result,indent=2,sort_keys=True))
    failed={key:(result['measurements'][key],limit) for key,limit in result['budgets'].items() if result['measurements'][key]>limit}
    if failed:raise SystemExit('Performance budget exceeded: '+repr(failed))

if __name__=='__main__':main()

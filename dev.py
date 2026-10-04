import argparse
from mv_server import run_app
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--browser',action='store_true');p.add_argument('--data-dir');p.add_argument('--port',type=int,default=0);a=p.parse_args()
    run_app(a.data_dir,a.browser,a.port)

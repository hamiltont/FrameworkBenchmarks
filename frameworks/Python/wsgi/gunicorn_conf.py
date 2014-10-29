import multiprocessing
import os
import sys

# Quick hack to patch the detected CPU cores
sys.path.append('.')
sys.path.append('/root/FrameworkBenchmarks/toolset/benchmark')
from utils import available_cpu_count

_is_pypy = hasattr(sys, 'pypy_version_info')
_is_travis = os.environ.get('TRAVIS') == 'true'

# only implements json and plain. Not wait DB.
workers = available_cpu_count()
if _is_travis:
    workers = 2

bind = "0.0.0.0:8080"
keepalive = 120
errorlog = '-'
pidfile = 'gunicorn.pid'

if _is_pypy:
    worker_class = "tornado"
else:
    worker_class = "meinheld.gmeinheld.MeinheldWorker"

    def post_fork(server, worker):
        # Disalbe access log
        import meinheld.server
        meinheld.server.set_access_logger(None)


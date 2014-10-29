import subprocess
import sys
import setup_util
import os
import multiprocessing

def start(args, logfile, errfile):
  setup_util.replace_text("openresty/nginx.conf", "CWD", args.troot)
  setup_util.replace_text("openresty/app.lua", "DBHOSTNAME", args.database_host)

  threads = multiprocessing.cpu_count()
  logfile.write("Starting %s workers\n\n" % threads)
  logfile.flush()
  errfile.write("Starting %s workers\n\n" % threads)
  errfile.flush()
  print "Starting %s workers" %  threads
  subprocess.Popen('sudo /usr/local/openresty/nginx/sbin/nginx -c $TROOT/nginx.conf -g "worker_processes ' + str(threads) + ';"', shell=True, cwd="openresty", stderr=errfile, stdout=logfile)
  return 0

def stop(logfile, errfile):
  subprocess.Popen('sudo /usr/local/openresty/nginx/sbin/nginx -c $TROOT/nginx.conf -s stop', shell=True, cwd="openresty", stderr=errfile, stdout=logfile)

  return 0

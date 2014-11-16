from setup.linux.installer import Installer
from setup.linux import setup_util

from benchmark import framework_test
from benchmark.test_types import *
from utils import header
from utils import gather_tests
from utils import gather_frameworks
from utils import available_cpu_count

import os
import json
import subprocess
import traceback
import time
import pprint
import csv
import sys
import logging
import socket
import threading
import textwrap
import uuid
from pprint import pprint

from multiprocessing import Process

from datetime import datetime

# Cross-platform colored text
from colorama import Fore, Back, Style

# Text-based progress indicators
import progressbar

class Benchmarker:

  ##########################################################################################
  # Public methods
  ##########################################################################################

  ############################################################
  # Prints all the available tests
  ############################################################
  def run_list_tests(self):
    all_tests = self.__gather_tests

    for test in all_tests:
      print test.name

    self.__finish()
  ############################################################
  # End run_list_tests
  ############################################################

  ############################################################
  # Prints the metadata for all the available tests
  ############################################################
  def run_list_test_metadata(self):
    all_tests = self.__gather_tests
    all_tests_json = json.dumps(map(lambda test: {
      "name": test.name,
      "approach": test.approach,
      "classification": test.classification,
      "database": test.database,
      "framework": test.framework,
      "language": test.language,
      "orm": test.orm,
      "platform": test.platform,
      "webserver": test.webserver,
      "os": test.os,
      "database_os": test.database_os,
      "display_name": test.display_name,
      "notes": test.notes,
      "versus": test.versus
    }, all_tests))

    with open(os.path.join(self.full_results_directory(), "test_metadata.json"), "w") as f:
      f.write(all_tests_json)

    self.__finish()


  ############################################################
  # End run_list_test_metadata
  ############################################################
  
  ############################################################
  # parse_timestamp
  # Re-parses the raw data for a given timestamp
  ############################################################
  def parse_timestamp(self):
    all_tests = self.__gather_tests

    for test in all_tests:
      test.parse_all()
    
    self.__parse_results(all_tests)

    self.__finish()

  ############################################################
  # End parse_timestamp
  ############################################################

  ############################################################
  # Run the tests:
  # This process involves setting up the client/server machines
  # with any necessary change. Then going through each test,
  # running their setup script, verifying the URLs, and
  # running benchmarks against them.
  ############################################################
  def run(self):
    ##########################
    # Get a list of all known
    # tests that we can run.
    ##########################    
    all_tests = self.__gather_tests

    if self.docker or self.docker_client: 
      return self._run_docker(all_tests)

    ##########################
    # Setup client/server
    ##########################
    print header("Preparing Server, Database, and Client ...", top='=', bottom='=')
    self.__setup_server()
    self.__setup_database()
    self.__setup_client()

    ## Check if wrk (and wrk-pipeline) is installed and executable, if not, raise an exception
    #if not (os.access("/usr/local/bin/wrk", os.X_OK) and os.access("/usr/local/bin/wrk-pipeline", os.X_OK)):
    #  raise Exception("wrk and/or wrk-pipeline are not properly installed. Not running tests.")

    ##########################
    # Run tests
    ##########################
    print header("Running Tests...", top='=', bottom='=')
    result = self.__run_tests(all_tests)

    ##########################
    # Parse results
    ##########################  
    if self.mode == "benchmark":
      print header("Parsing Results ...", top='=', bottom='=')
      self.__parse_results(all_tests)

    self.__finish()
    return result

  ############################################################
  # End run
  ############################################################

  # Called for both --docker and --docker-client
  def _run_docker(self, all_tests):
    in_container = self.docker_client
    
    if not in_container: 
      print header("Preparing Server, Database, and Client ...", top='=', bottom='=')
      self.__setup_server()
      self.__setup_database()
      self.__setup_client()
    else:
      self.__setup_server()

    # No need to print the same message twice
    if not in_container:
      print header("Running Tests ...", top='=', bottom='=')
    self.__run_tests(all_tests)

    ##########################
    # Parse results
    ##########################  
    if self.mode == "benchmark" and not self.docker_client:
      print header("Parsing Results ...", top='=', bottom='=')
      self.__parse_results(all_tests)

    if not self.docker_client: 
      self.__finish()

  ############################################################
  # database_sftp_string(batch_file)
  # generates a fully qualified URL for sftp to database
  ############################################################
  def database_sftp_string(self, batch_file):
    sftp_string =  "sftp -oStrictHostKeyChecking=no "
    if batch_file != None: sftp_string += " -b " + batch_file + " "

    if self.database_identity_file != None:
      sftp_string += " -i " + self.database_identity_file + " "

    return sftp_string + self.database_user + "@" + self.database_host
  ############################################################
  # End database_sftp_string
  ############################################################

  ############################################################
  # client_sftp_string(batch_file)
  # generates a fully qualified URL for sftp to client
  ############################################################
  def client_sftp_string(self, batch_file):
    sftp_string =  "sftp -oStrictHostKeyChecking=no "
    if batch_file != None: sftp_string += " -b " + batch_file + " "

    if self.client_identity_file != None:
      sftp_string += " -i " + self.client_identity_file + " "

    return sftp_string + self.client_user + "@" + self.client_host
  ############################################################
  # End client_sftp_string
  ############################################################

  ############################################################
  # generate_url(url, port)
  # generates a fully qualified URL for accessing a test url
  ############################################################
  def generate_url(self, url, port):
    return self.server_host + ":" + str(port) + url
  ############################################################
  # End generate_url
  ############################################################

  ############################################################
  # get_output_file(test_name, test_type)
  # returns the output file name for this test_name and 
  # test_type timestamp/test_type/test_name/raw 
  ############################################################
  def get_output_file(self, test_name, test_type):
    return os.path.join(self.result_directory, self.timestamp, test_type, test_name, "raw")
  ############################################################
  # End get_output_file
  ############################################################

  ############################################################
  # output_file(test_name, test_type)
  # returns the output file for this test_name and test_type
  # timestamp/test_type/test_name/raw 
  ############################################################
  def output_file(self, test_name, test_type):
    output_file = self.get_output_file(test_name, test_type)
    try:
      os.makedirs(os.path.dirname(output_file))
    except OSError:
      pass
    
    # If we are running inside docker, we have to ensure that 
    # the folder permissions are set to allow non-root users 
    # to create new files inside of this directory 
    if self.docker_client:
      path=os.path.join(self.result_directory, self.timestamp)
      os.chmod(path, 0777)

    return output_file
  ############################################################
  # End output_file
  ############################################################


  ############################################################
  # get_stats_file(test_name, test_type)
  # returns the stats file name for this test_name and 
  # test_type timestamp/test_type/test_name/raw 
  ############################################################
  def get_stats_file(self, test_name, test_type):
    return os.path.join(self.result_directory, self.timestamp, test_type, test_name, "stats")
  ############################################################
  # End get_stats_file
  ############################################################


  ############################################################
  # stats_file(test_name, test_type)
  # returns the stats file for this test_name and test_type
  # timestamp/test_type/test_name/raw 
  ############################################################
  def stats_file(self, test_name, test_type):
      path = self.get_stats_file(test_name, test_type)
      try:
        os.makedirs(os.path.dirname(path))
      except OSError:
        pass
      return path
  ############################################################
  # End stats_file
  ############################################################
  

  ############################################################
  # full_results_directory
  ############################################################
  def full_results_directory(self):
    path = os.path.join(self.result_directory, self.timestamp)
    try:
      os.makedirs(path)
    except OSError:
      pass
    return path
  ############################################################
  # End full_results_directory
  ############################################################

  ############################################################
  # Latest intermediate results dirctory
  ############################################################

  def latest_results_directory(self):
    path = os.path.join(self.result_directory,"latest")
    try:
      os.makedirs(path)
    except OSError:
      pass
    return path

  ############################################################
  # report_verify_results
  # Used by FrameworkTest to add verification details to our results
  #
  # TODO: Technically this is an IPC violation - we are accessing
  # the parent process' memory from the child process
  ############################################################
  def report_verify_results(self, framework, test, result):
    if framework.name not in self.results['verify'].keys():
      self.results['verify'][framework.name] = dict()
    self.results['verify'][framework.name][test] = result

  ############################################################
  # report_benchmark_results
  # Used by FrameworkTest to add benchmark data to this
  #
  # TODO: Technically this is an IPC violation - we are accessing
  # the parent process' memory from the child process
  ############################################################
  def report_benchmark_results(self, framework, test, results):
    if test not in self.results['rawData'].keys():
      self.results['rawData'][test] = dict()

    # If results has a size from the parse, then it succeeded.
    if results:
      self.results['rawData'][test][framework.name] = results

      # This may already be set for single-tests
      if framework.name not in self.results['succeeded'][test]:
        self.results['succeeded'][test].append(framework.name)
    else:
      # This may already be set for single-tests
      if framework.name not in self.results['failed'][test]:
        self.results['failed'][test].append(framework.name)

  ############################################################
  # End report_results
  ############################################################

  ##########################################################################################
  # Private methods
  ##########################################################################################

  ############################################################
  # Gathers all the tests
  ############################################################
  @property
  def __gather_tests(self):
    tests = gather_tests(include=self.test, 
      exclude=self.exclude,
      benchmarker=self)

    # If the tests have been interrupted somehow, then we want to resume them where we left
    # off, rather than starting from the beginning
    if os.path.isfile('current_benchmark.txt'):
        with open('current_benchmark.txt', 'r') as interrupted_benchmark:
            interrupt_bench = interrupted_benchmark.read().strip()
            for index, atest in enumerate(tests):
                if atest.name == interrupt_bench:
                    tests = tests[index:]
                    break
    return tests
  ############################################################
  # End __gather_tests
  ############################################################

  ############################################################
  # Makes any necessary changes to the server that should be 
  # made before running the tests. This involves setting kernal
  # settings to allow for more connections, or more file
  # descriptiors
  #
  # http://redmine.lighttpd.net/projects/weighttp/wiki#Troubleshooting
  ############################################################
  def __setup_server(self):
    try:
      if os.name == 'nt':
        return True
      subprocess.check_call(["sudo","bash","-c","cd /sys/devices/system/cpu; ls -d cpu[0-9]*|while read x; do echo performance > $x/cpufreq/scaling_governor; done"])
      subprocess.check_call("sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65535".rsplit(" "))
      subprocess.check_call("sudo sysctl -w net.core.somaxconn=65535".rsplit(" "))
      subprocess.check_call("sudo -s ulimit -n 65535".rsplit(" "))
      subprocess.check_call("sudo sysctl net.ipv4.tcp_tw_reuse=1".rsplit(" "))
      subprocess.check_call("sudo sysctl net.ipv4.tcp_tw_recycle=1".rsplit(" "))
      subprocess.check_call("sudo sysctl -w kernel.shmmax=134217728".rsplit(" "))
      subprocess.check_call("sudo sysctl -w kernel.shmall=2097152".rsplit(" "))
    except subprocess.CalledProcessError:
      return False
  ############################################################
  # End __setup_server
  ############################################################

  ############################################################
  # Makes any necessary changes to the database machine that 
  # should be made before running the tests. Is very similar
  # to the server setup, but may also include database specific
  # changes.
  ############################################################
  def __setup_database(self):
    p = subprocess.Popen(self.database_ssh_string, stdin=subprocess.PIPE, shell=True)
    p.communicate("""
      sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65535
      sudo sysctl -w net.core.somaxconn=65535
      sudo -s ulimit -n 65535
      sudo sysctl net.ipv4.tcp_tw_reuse=1
      sudo sysctl net.ipv4.tcp_tw_recycle=1
      sudo sysctl -w kernel.shmmax=2147483648
      sudo sysctl -w kernel.shmall=2097152
    """)
  ############################################################
  # End __setup_database
  ############################################################

  ############################################################
  # Makes any necessary changes to the client machine that 
  # should be made before running the tests. Is very similar
  # to the server setup, but may also include client specific
  # changes.
  ############################################################
  def __setup_client(self):
    p = subprocess.Popen(self.client_ssh_string, stdin=subprocess.PIPE, shell=True)
    p.communicate("""
      sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65535
      sudo sysctl -w net.core.somaxconn=65535
      sudo -s ulimit -n 65535
      sudo sysctl net.ipv4.tcp_tw_reuse=1
      sudo sysctl net.ipv4.tcp_tw_recycle=1
      sudo sysctl -w kernel.shmmax=2147483648
      sudo sysctl -w kernel.shmall=2097152
    """)
  ############################################################
  # End __setup_client
  ############################################################

  ############################################################
  # __run_tests
  #
  # 2013-10-02 ASB  Calls each test passed in tests to
  #                 __run_test in a separate process.  Each
  #                 test is given a set amount of time and if
  #                 kills the child process (and subsequently
  #                 all of its child processes).  Uses
  #                 multiprocessing module.
  ############################################################

  def __run_tests(self, tests):
    if len(tests) == 0:
      return 0

    logging.debug("Start __run_tests.")
    logging.debug("__name__ = %s",__name__)

    error_happened = False
    if self.os.lower() == 'windows':
      logging.debug("Executing __run_tests on Windows")
      for test in tests:
        with open('current_benchmark.txt', 'w') as benchmark_resume_file:
          benchmark_resume_file.write(test.name)
        if self.__run_test(test) != 0:
          error_happened = True
    else:
      logging.debug("Executing __run_tests on Linux")

      # Setup a nice progressbar and ETA indicator
      widgets = [self.mode, ': ',  progressbar.Percentage(), 
                 ' ', progressbar.Bar(),
                 ' Rough ', progressbar.ETA()]
      pbar = progressbar.ProgressBar(widgets=widgets, maxval=len(tests)).start()
      pbar_test = 0

      # These features do not work on Windows
      for test in tests:
        pbar.update(pbar_test)
        pbar_test = pbar_test + 1
        if __name__ == 'benchmark.benchmarker':
          if self.docker: 
            print header("Running Test Container For: %s ..." % test.name)
            test_process = Process(target=self.__run_test_in_container, args=(test,))
          else: 
            print header("Running Test: %s" % test.name)
            with open('current_benchmark.txt', 'w') as benchmark_resume_file:
              benchmark_resume_file.write(test.name)
            test_process = Process(target=self.__run_test, name="Test Runner (%s)" % test.name, args=(test,))
            
          test_process.start()
          test_process.join(self.run_test_timeout_seconds)
          self.__load_results()  # Load intermediate result from child process
          if(test_process.is_alive()):
            logging.debug("Child process for {name} is still alive. Terminating.".format(name=test.name))
            self.__write_intermediate_results(test.name,"__run_test timeout (="+ str(self.run_test_timeout_seconds) + " seconds)")
            test_process.terminate()
            test_process.join()
          if test_process.exitcode != 0:
            error_happened = True
      pbar.finish()
    if os.path.isfile('current_benchmark.txt'):
      os.remove('current_benchmark.txt')

    logging.info("End __run_tests")
    if error_happened:
      return 1
    return 0
  ############################################################
  # End __run_tests
  ############################################################

  def __run_test_in_container(self, test):
    user = subprocess.check_output("printf $USER", shell=True)
    test_dir_name = os.path.relpath(test.directory, self.fwroot)[11:].replace('/','-').lower()
    repo="%s/tfb-%s" % (user, test_dir_name)
    if not setup_util.exists(repo):
      print "DOCKER: Unable to run %s, image %s does not exist" % (test.name, repo)
      return

    # Ensure container is not already running
    c = setup_util.get_client()
    for container in c.containers():
      if container['Image'].startswith(repo):
        print "DOCKER: ERROR - Container %s already running. Killing" % repo
        c.stop(container, timeout=15)

    # Need to solve https://github.com/docker/docker/issues/3778 so that 
    # we can let docker's NAT handle port binding on the host. 
    # To do this I create a randomly-named mapping file and bind it inside 
    # the container. Once I've started the container, I determine the port
    # that was used for test.port and write it into that file. The file is 
    # only read by run_test before benchmarking, whcih happens after the 
    # "sleep to ensure framework is ready", so I'm not concerned about it being
    # read before I've written to it
    # Wish I could use the container ID in the filename, but I need the command 
    # before I get the cid, so I cannot
    maps_dir = "%s/toolset/mappings" % self.fwroot
    if not os.path.exists(maps_dir):
      os.makedirs(maps_dir)
    map_filepath = "%s/%s-%s" % (maps_dir, test.name, str(uuid.uuid4())[:7])  
    print "DOCKER: Placing port mapping inside %s" % os.path.relpath(map_filepath, self.fwroot)
    
    # Build run command
    command="toolset/run-tests.py --test %s --docker-client --verbose" % test.name
    command="%s --time %s" % (command, self.timestamp) # We only want one directory for results
    command="%s --mode %s" % (command, self.mode)
    command="%s --name %s" % (command, self.name)
    command="%s --type %s" % (command, self.type)
    command="%s --duration %s" % (command, self.duration)
    command="%s --sleep %s" % (command, self.sleep)
    command="%s --concurrency-levels %s" % (command, ",".join(map(str, self.concurrency_levels)))
    command="%s --threads %s" % (command, self.threads)
    command="%s --query-levels %s" % (command, ",".join(map(str, self.query_levels)))
    command="%s --server-host %s" % (command, self.server_host)
    command="%s --client-host %s" % (command, self.client_host)
    command="%s --database-host %s" % (command, self.database_host)
    command="%s --client-user %s" % (command, self.client_user)
    command="%s --database-user %s" % (command, self.database_user)
    command="%s --docker-port-file %s" % (command, os.path.relpath(map_filepath, self.fwroot))
    if self.docker_no_server_stop:
      print "DOCKER: Using no-server-stop mode. Going to start server, then sleep TFB"
      command="%s --docker-no-server-stop" % command

    # Handle SSH identity files
    # Allows multiple path types e.g. foo, ../foo, ~/foo
    ci=os.path.abspath(os.path.expanduser(self.client_identity_file))
    ci_path = os.path.dirname(ci)
    ci_file = os.path.basename(ci)
    if ci_path == os.path.expanduser("~/.ssh"):
      command="%s --client-identity-file /root/.ssh/%s" % (command, ci_file)
      ci_mount = None
    else:
      # Bind mount, then copy so we can chown
      # TODO I hate this. You could accidentally share your keys wiht the world via a push
      # if you try and save this container
      command="%s --client-identity-file /tmp/sshclient/%s" % (command, ci_file)
      ci_mount = {ci_path: {'bind': '/tmp/zz_sshclient'}}
      command="cp -R /tmp/zz_sshclient /tmp/sshclient && chown -R root:root /tmp/sshclient && %s" % command  
    
    di=os.path.abspath(os.path.expanduser(self.database_identity_file))
    di_path = os.path.dirname(di)
    di_file = os.path.basename(di)
    if di_path == os.path.expanduser("~/.ssh"):
      command="%s --database-identity-file /root/.ssh/%s" % (command, di_file)    
      di_mount = None
    else:
      # TODO I hate this so much I'm leaving two comments
      command="%s --database-identity-file /tmp/sshdb/%s" % (command, di_file)    
      di_mount = {di_path: {'bind': '/tmp/zz_sshdb'}}
      command="cp -R /tmp/zz_sshdb /tmp/sshdb && chown -R root:root /tmp/sshdb && %s" % command  

    # Create container to run this test
    #
    #   - base on installation container
    #   - command is benchmark command
    #   - mount toolset directory in case you're a developer making changes
    #   - mount results directory to use in container
    #   - mount ~/.ssh in case they have a config file with keys defined
    #     TODO: check what happens if .ssh doesn't exist
    #   - mount folders for identity file locations
    #   - mount this test's directory in case the contents have been updated
    #     since the prereq folder was built

    # Bind mount ssh, then copy so we can chown it
    ssh_volume="/tmp/zz_ssh" 
    command="cp -R /tmp/zz_ssh /root/.ssh && chown -R root:root /root/.ssh && %s" % command  
    toolvolume="/root/FrameworkBenchmarks/toolset"
    reslvolume="/root/FrameworkBenchmarks/results"
    testvolume="/root/FrameworkBenchmarks/%s" % os.path.relpath(test.directory, self.fwroot)

    # docker-py can only run one command (e.g. no &&), so we 
    # run bash as our one and pass it the command we really want
    command="bash -c \"%s\"" % command
    install_container = c.create_container(repo, command=command,
      volumes=[toolvolume, reslvolume, ssh_volume, testvolume],
      ports = [int(test.port)])
    cid = install_container['Id']

    # Run the test
    print "DOCKER: Preparing to run %s in container %s" % (test.name, cid)

    tool_dir = "%s/toolset" % self.fwroot
    resl_dir = "%s/results" % self.fwroot
    ssh__dir = os.path.expanduser("~/.ssh")
    test_dir = test.directory
    mounts={
      resl_dir: { 'bind': reslvolume}, 
      tool_dir: { 'bind': toolvolume},
      ssh__dir: { 'bind': ssh_volume},
      test_dir: { 'bind': testvolume}
      }
    if ci_mount: 
      mounts.update(ci_mount)
    if di_mount: 
      mounts.update(di_mount)

    vols = ""
    for host_path in mounts.keys():
      vols="%s -v %s:%s" % (vols, host_path, mounts[host_path]['bind'])

    lxc_options = {}  
    if -1 in self.docker_server_cpuset:
      print "DOCKER: Disabling CPU pinning"
    else:
      lxc_options['lxc.cgroup.cpuset.cpus'] = ",".join(str(x) for x in self.docker_server_cpuset)
      print "DOCKER: Allowing processors [%s]" % lxc_options['lxc.cgroup.cpuset.cpus']
    
    if -1 == self.docker_server_cpu:
      print "DOCKER: Disabling CFS bandwidth limits"
    else:
      # 500ms period. See Turner et al. "CPU bandwidth control for CFS"
      lxc_options['lxc.cgroup.cpu.cfs_period_us'] = 500 * 1000
      total_bandwidth = lxc_options['lxc.cgroup.cpu.cfs_period_us'] * len(self.docker_server_cpuset)
      lxc_options['lxc.cgroup.cpu.cfs_quota_us'] =  total_bandwidth * self.docker_server_cpu / 100
      print "DOCKER: Allowing up to %s%% CPU time (total of %s CPUs allowed - %s / %s)" % (self.docker_server_cpu, len(self.docker_server_cpuset), lxc_options['lxc.cgroup.cpu.cfs_quota_us'], total_bandwidth)
  
    # Set (swap+ram)==(ram) to disable swap
    # See http://stackoverflow.com/a/26482080/119592
    lxc_options['lxc.cgroup.memory.max_usage_in_bytes']= "%sM" % self.docker_server_ram
    lxc_options['lxc.cgroup.memory.limit_in_bytes']    = "%sM" % self.docker_server_ram
    print "DOCKER: Allowing %s MB real RAM" % self.docker_server_ram
  
    lxc = " ".join([ "--lxc-conf=\"%s=%s\""%(k,v) for k,v in lxc_options.iteritems()])
    print "DOCKER: Running this monstrosity: sudo docker run %s --net='host' -i -t %s %s /bin/sh -c '%s'" % (lxc, vols, repo, command)
    
    c.start(cid, binds=mounts, 
      port_bindings={test.port: None}, lxc_conf=lxc_options)

    map_port = c.port(cid, test.port)[0]['HostPort']
    print "DOCKER: Fetching port mapping: docker port %s %s" % (cid, test.port)
    print "DOCKER: Found %s mapped to host port %s" % (test.port, map_port)

    map_file = open(map_filepath, 'w')
    map_file.write(map_port)
    map_file.close()

    # Fetch container output
    last_had_newline = True
    output = c.attach(cid, stream=True)
    for line in output:
      if last_had_newline: 
        sys.stdout.write("%s: %s" % (repo, line))
      else:
        sys.stdout.write(line)
      last_had_newline = line.endswith("\n")

    # Check container exit code
    exit = c.wait(cid)
    if exit != 0: 
      print "DOCKER: Non-zero exit when running %s in %s, expect failures\n" % (test.name, cid)
      print "DOCKER: Storing %s in %s for you to review\n" % (test.name, "rxx-%s" % repo)
      c.commit(cid, repository="rxx-%s"%repo, tag='latest')

  ############################################################
  # __run_test
  # 2013-10-02 ASB  Previously __run_tests.  This code now only
  #                 processes a single test.
  #
  # Ensures that the system has all necessary software to run
  # the tests. This does not include that software for the individual
  # test, but covers software such as curl and weighttp that
  # are needed.
  ############################################################
  def __run_test(self, test):
    
    # Used to capture return values 
    def exit_with_code(code):
      if self.os.lower() == 'windows':
        return code
      else:
        sys.exit(code)

    try:
      os.makedirs(os.path.join(self.latest_results_directory, 'logs', "{name}".format(name=test.name)))
    except:
      pass
    with open(os.path.join(self.latest_results_directory, 'logs', "{name}".format(name=test.name), 'out.txt'), 'w') as out, \
         open(os.path.join(self.latest_results_directory, 'logs', "{name}".format(name=test.name), 'err.txt'), 'w') as err:

      if test.os.lower() != self.os.lower() or test.database_os.lower() != self.database_os.lower():
        out.write("OS or Database OS specified in benchmark_config does not match the current environment. Skipping.\n")
        return exit_with_code(0)
      
      # If the test is in the excludes list, we skip it
      if self.exclude != None and test.name in self.exclude:
        out.write("Test {name} has been added to the excludes list. Skipping.\n".format(name=test.name))
        return exit_with_code(0)

      out.write("test.os.lower() = {os}  test.database_os.lower() = {dbos}\n".format(os=test.os.lower(),dbos=test.database_os.lower()))
      out.write("self.results['frameworks'] != None: {val}\n".format(val=str(self.results['frameworks'] != None)))
      out.write("test.name: {name}\n".format(name=str(test.name)))
      out.write("self.results['completed']: {completed}\n".format(completed=str(self.results['completed'])))
      #if self.results['frameworks'] != None and test.name in self.results['completed']:
      #  out.write('Framework {name} found in latest saved data. Skipping.\n'.format(name=str(test.name)))
      #  return exit_with_code(1)
      out.flush()

      out.write(header("Beginning %s" % test.name, top='='))
      out.flush()

      ##########################
      # Start this test
      ##########################  
      out.write(header("Starting %s" % test.name))
      out.flush()
      try:
        if test.requires_database():
          p = subprocess.Popen(self.database_ssh_string, stdin=subprocess.PIPE, stdout=out, stderr=err, shell=True)
          p.communicate("""
            sudo restart mysql
            sudo restart mongodb
            sudo service redis-server restart
            sudo /etc/init.d/postgresql restart
          """)
          time.sleep(10)

        if self.__is_port_bound(test.port):
          err.write(header("Error: Port %s is not available, attempting to recover" % test.port))
          err.flush()
          print "Error: Port %s is not available, attempting to recover" % test.port
          self.__forciblyEndPortBoundProcesses(test.port, out, err)
          if self.__is_port_bound(test.port):
            self.__write_intermediate_results(test.name, "port " + str(test.port) + " is not available before start")
            err.write(header("Error: Port %s is not available, cannot start %s" % (test.port, test.name)))
            err.flush()
            print "Error: Unable to recover port, cannot start test"
            return exit_with_code(1)

        result = test.start(out, err)
        if result != 0: 
          test.stop(out, err)
          time.sleep(5)
          err.write( "ERROR: Problem starting {name}\n".format(name=test.name) )
          err.write(header("Stopped %s" % test.name))
          err.flush()
          self.__write_intermediate_results(test.name,"<setup.py>#start() returned non-zero")
          return exit_with_code(1)
        
        logging.info("Sleeping %s seconds to ensure framework is ready" % self.sleep)
        time.sleep(self.sleep)

        ##########################
        # Verify URLs
        ##########################
        logging.info("Verifying framework URLs")
        passed_verify = test.verify_urls(out, err)
        out.flush()
        err.flush()

        if self.docker_client and self.docker_no_server_stop:
          out.write(header("Not benchmarking %s, or calling server stop function." % test.name))
          out.write("It's alive, now have your fun. This process is sleeping for 30 minutes, then exiting")
          out.flush()
          time.sleep(60*30)
          return exit_with_code(0)

        ##########################
        # Benchmark this test
        ##########################
        if self.mode == "benchmark":
          logging.info("Benchmarking")
          out.write(header("Benchmarking %s" % test.name))
          out.flush()
          test.benchmark(out, err)
          out.flush()
          err.flush()

        ##########################
        # Stop this test
        ##########################
        out.write(header("Stopping %s" % test.name))
        out.flush()
        test.stop(out, err)
        out.flush()
        err.flush()
        time.sleep(5)

        if self.__is_port_bound(test.port):
          err.write("Port %s was not freed. Attempting to free it." % (test.port, ))
          err.flush()
          self.__forciblyEndPortBoundProcesses(test.port, out, err)
          time.sleep(5)
          if self.__is_port_bound(test.port):
            err.write(header("Error: Port %s was not released by stop %s" % (test.port, test.name)))
            err.flush()
            self.__write_intermediate_results(test.name, "port " + str(test.port) + " was not released by stop")

          return exit_with_code(1)

        out.write(header("Stopped %s" % test.name))
        out.flush()
        time.sleep(5)

        ##########################################################
        # Save results thus far into toolset/benchmark/latest.json
        ##########################################################

        out.write(header("Saving results through %s" % test.name))
        out.flush()
        self.__write_intermediate_results(test.name,time.strftime("%Y%m%d%H%M%S", time.localtime()))

        if self.mode == "verify" and not passed_verify:
          print "Failed verify!"
          return exit_with_code(1)
      except (OSError, IOError, subprocess.CalledProcessError) as e:
        self.__write_intermediate_results(test.name,"<setup.py> raised an exception")
        err.write(header("Subprocess Error %s" % test.name))
        traceback.print_exc(file=err)
        err.flush()
        try:
          test.stop(out, err)
        except (subprocess.CalledProcessError) as e:
          self.__write_intermediate_results(test.name,"<setup.py>#stop() raised an error")
          err.write(header("Subprocess Error: Test .stop() raised exception %s" % test.name))
          traceback.print_exc(file=err)
          err.flush()
        out.close()
        err.close()
        return exit_with_code(1)
      # TODO - subprocess should not catch this exception!
      # Parent process should catch it and cleanup/exit
      except (KeyboardInterrupt) as e:
        test.stop(out, err)
        out.write(header("Cleaning up..."))
        out.flush()
        self.__finish()
        sys.exit(1)

      out.close()
      err.close()
      return exit_with_code(0)

  ############################################################
  # End __run_tests
  ############################################################

  ############################################################
  # __is_port_bound
  # Check if the requested port is available. If it
  # isn't available, then a previous test probably didn't
  # shutdown properly.
  ############################################################
  def __is_port_bound(self, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
      # Try to bind to all IP addresses, this port
      s.bind(("", port))
      # If we get here, we were able to bind successfully,
      # which means the port is free.
    except:
      # If we get an exception, it might be because the port is still bound
      # which would be bad, or maybe it is a privileged port (<1024) and we
      # are not running as root, or maybe the server is gone, but sockets are
      # still in TIME_WAIT (SO_REUSEADDR). To determine which scenario, try to
      # connect.
      try:
        s.connect(("127.0.0.1", port))
        # If we get here, we were able to connect to something, which means
        # that the port is still bound.
        return True
      except:
        # An exception means that we couldn't connect, so a server probably
        # isn't still running on the port.
        pass
    finally:
      s.close()

    return False

  ############################################################
  # End __is_port_bound
  ############################################################

  def __forciblyEndPortBoundProcesses(self, test_port, out, err):
    p = subprocess.Popen(['sudo', 'netstat', '-lnp'], stdout=subprocess.PIPE)
    (ns_out, ns_err) = p.communicate()
    for line in ns_out.splitlines():
      if 'tcp' in line and not 'tcp6' in line:
        splitline = line.split()
        port = splitline[3].split(':')
        port = int(port[len(port) - 1].strip())

        if port > 6000:
          pid = splitline[6].split('/')[0].strip()
          ps = subprocess.Popen(['ps','p',pid], stdout=subprocess.PIPE)
          (out_6000, err_6000) = ps.communicate()
          err.write(textwrap.dedent(
          """
          Port {port} should not be open. See the following lines for information
          {netstat}
          {ps}
          """.format(port=port, netstat=line, ps=out_6000)))
          err.flush()
        if port == test_port:
          err.write( header("Error: Test port %s should not be open" % port, bottom='') )
          try:
            pid = splitline[6].split('/')[0].strip()
            ps = subprocess.Popen(['ps','p',pid], stdout=subprocess.PIPE)
            # Store some info about this process
            (out_15, err_15) = ps.communicate()
            err.write("  Sending SIGTERM to this process:\n  %s\n" % out_15)
            os.kill(int(pid), 15)
            # Sleep for 10 sec; kill can be finicky
            time.sleep(10)

            # Check that PID again
            ps = subprocess.Popen(['ps','p',pid], stdout=subprocess.PIPE)
            (out_9, err_9) = ps.communicate()
            if len(out_9.splitlines()) != 1:  # One line for the header row
              err.write("  Process is still alive!\n")
              err.write("  Sending SIGKILL to this process:\n   %s\n" % out_9)
              os.kill(int(pid), 9)
            else:
              err.write("  Process has been terminated\n")
          except OSError:
            out.write( "  Error: Could not kill pid %s\n" % pid )
            # This is okay; likely we killed a parent that ended
            # up automatically killing this before we could.
          err.write( header("Done attempting to recover port %s" % port, top='') )

  ############################################################
  # __parse_results
  # Ensures that the system has all necessary software to run
  # the tests. This does not include that software for the individual
  # test, but covers software such as curl and weighttp that
  # are needed.
  ############################################################
  def __parse_results(self, tests):
    # Run the method to get the commmit count of each framework.
    # self.__count_commits()
   # Call the method which counts the sloc for each framework
    # self.__count_sloc()

    # Time to create parsed files
    # Aggregate JSON file
    with open(os.path.join(self.full_results_directory(), "results.json"), "w") as f:
      f.write(json.dumps(self.results, indent=2))

    # If we just accessed results.json from inside docker, 
    # we need to expand the permissions so that the parent
    # process will be able to write to results.json once we've
    # finished
    if self.docker_client:
      print "DOCKER: Accessed parse_results from inside a container. Is this expected?"
      path = os.path.join(self.full_results_directory(), "results.json")
      os.chmod(path, 0777)

  ############################################################
  # End __parse_results
  ############################################################


  #############################################################
  # __count_sloc
  #############################################################
  def __count_sloc(self):
    frameworks = gather_frameworks(include=self.test,
      exclude=self.exclude, benchmarker=self)
    
    jsonResult = {}
    for framework, testlist in frameworks.iteritems():
      if not os.path.exists(os.path.join(testlist[0].directory, "source_code")):
        logging.warn("Cannot count lines of code for %s - no 'source_code' file", framework)
        continue

      # Unfortunately the source_code files use lines like
      # ./cpoll_cppsp/www/fortune_old instead of 
      # ./www/fortune_old
      # so we have to back our working dir up one level
      wd = os.path.dirname(testlist[0].directory)
      
      try:
        command = "cloc --list-file=%s/source_code --yaml" % testlist[0].directory
        # Find the last instance of the word 'code' in the yaml output. This should
        # be the line count for the sum of all listed files or just the line count
        # for the last file in the case where there's only one file listed.
        command = command + "| grep code | tail -1 | cut -d: -f 2"
        logging.debug("Running \"%s\" (cwd=%s)", command, wd)
        lineCount = subprocess.check_output(command, cwd=wd, shell=True)
        jsonResult[framework] = int(lineCount)
      except subprocess.CalledProcessError:
        continue
      except ValueError as ve:
        logging.warn("Unable to get linecount for %s due to error '%s'", framework, ve)
    self.results['rawData']['slocCounts'] = jsonResult
  ############################################################
  # End __count_sloc
  ############################################################

  ############################################################
  # __count_commits
  #
  ############################################################
  def __count_commits(self):
    frameworks = gather_frameworks(include=self.test,
      exclude=self.exclude, benchmarker=self)

    def count_commit(directory, jsonResult):
      command = "git rev-list HEAD -- " + directory + " | sort -u | wc -l"
      try:
        commitCount = subprocess.check_output(command, shell=True)
        jsonResult[framework] = int(commitCount)
      except subprocess.CalledProcessError:
        pass

    # Because git can be slow when run in large batches, this 
    # calls git up to 4 times in parallel. Normal improvement is ~3-4x
    # in my trials, or ~100 seconds down to ~25
    # This is safe to parallelize as long as each thread only 
    # accesses one key in the dictionary
    threads = []
    jsonResult = {}
    t1 = datetime.now()
    for framework, testlist in frameworks.iteritems():
      directory = testlist[0].directory
      t = threading.Thread(target=count_commit, args=(directory,jsonResult))
      t.start()
      threads.append(t)
      # Git has internal locks, full parallel will just cause contention
      # and slowness, so we rate-limit a bit
      if len(threads) >= 4:
        threads[0].join()
        threads.remove(threads[0])

    # Wait for remaining threads
    for t in threads:
      t.join()
    t2 = datetime.now()
    # print "Took %s seconds " % (t2 - t1).seconds

    self.results['rawData']['commitCounts'] = jsonResult
    self.commits = jsonResult
  ############################################################
  # End __count_commits
  ############################################################

  ############################################################
  # __write_intermediate_results
  ############################################################
  def __write_intermediate_results(self,test_name,status_message):
    try:
      self.results["completed"][test_name] = status_message
      with open(os.path.join(self.latest_results_directory, 'results.json'), 'w') as f:
        f.write(json.dumps(self.results, indent=2))
    except (IOError):
      logging.error("Error writing results.json")

  ############################################################
  # End __write_intermediate_results
  ############################################################

  def __load_results(self):
    try:
      with open(os.path.join(self.latest_results_directory, 'results.json')) as f:
        results = json.load(f)
    except (ValueError, IOError):
      pass
    else:
      self.results = results

  ############################################################
  # __finish
  ############################################################
  def __finish(self):

    if hasattr(self, 'docker_client_container'):
      print "Stopping docker client container"
      c = setup_util.get_client()
      c.stop(self.docker_client_container, timeout=60)

    tests = self.__gather_tests
    # Normally you don't have to use Fore.BLUE before each line, but 
    # Travis-CI seems to reset color codes on newline (see travis-ci/travis-ci#2692)
    # or stream flush, so we have to ensure that the color code is printed repeatedly
    prefix = Fore.CYAN
    for line in header("Verification Summary", top='=', bottom='').split('\n'):
      print prefix + line
    for test in tests:
      print prefix + "| Test: %s" % test.name
      if test.name in self.results['verify'].keys():
        for test_type, result in self.results['verify'][test.name].iteritems():
          if result.upper() == "PASS":
            color = Fore.GREEN
          elif result.upper() == "WARN":
            color = Fore.YELLOW
          else:
            color = Fore.RED
          print prefix + "|       " + test_type.ljust(11) + ' : ' + color + result.upper()
      else:
        print prefix + "|      " + Fore.RED + "NO RESULTS (Did framework launch?)"
    print prefix + header('', top='', bottom='=') + Style.RESET_ALL

    print "Time to complete: " + str(int(time.time() - self.start_time)) + " seconds"
    print "Results are saved in " + os.path.join(self.result_directory, self.timestamp)

  ############################################################
  # End __finish
  ############################################################

  ##########################################################################################
  # Constructor
  ########################################################################################## 

  ############################################################
  # Initialize the benchmarker. The args are the arguments 
  # parsed via argparser.
  ############################################################
  def __init__(self, args):
    
    # Map type strings to their objects
    types = dict()
    types['json'] = JsonTestType()
    types['db'] = DBTestType()
    types['query'] = QueryTestType()
    types['fortune'] = FortuneTestType()
    types['update'] = UpdateTestType()
    types['plaintext'] = PlaintextTestType()

    # Turn type into a map instead of a string
    if args['type'] == 'all':
        args['types'] = types
    else:
        args['types'] = { args['type'] : types[args['type']] }

    args['max_threads'] = args['threads']

    self.__dict__.update(args)
    # pprint(self.__dict__)

    self.start_time = time.time()
    self.run_test_timeout_seconds = 3600

    # setup logging
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    
    # setup some additional variables
    if self.database_user == None: self.database_user = self.client_user
    if self.database_host == None: self.database_host = self.client_host
    if self.database_identity_file == None: self.database_identity_file = self.client_identity_file

    # Remember root directory
    self.fwroot = setup_util.get_fwroot()

    # setup results and latest_results directories 
    self.result_directory = os.path.join("results", self.name)
    self.latest_results_directory = self.latest_results_directory()
  
    if self.parse != None:
      self.timestamp = self.parse
    elif self.time != None:
      self.timestamp = self.time
    else:
      self.timestamp = time.strftime("%Y%m%d%H%M%S", time.localtime())
    
    # Load the latest data
    #self.latest = None
    #try:
    #  with open('toolset/benchmark/latest.json', 'r') as f:
    #    # Load json file into config object
    #    self.latest = json.load(f)
    #    logging.info("toolset/benchmark/latest.json loaded to self.latest")
    #    logging.debug("contents of latest.json: " + str(json.dumps(self.latest)))
    #except IOError:
    #  logging.warn("IOError on attempting to read toolset/benchmark/latest.json")
    #
    #self.results = None
    #try: 
    #  if self.latest != None and self.name in self.latest.keys():
    #    with open(os.path.join(self.result_directory, str(self.latest[self.name]), 'results.json'), 'r') as f:
    #      # Load json file into config object
    #      self.results = json.load(f)
    #except IOError:
    #  pass

    self.results = None
    try:
      with open(os.path.join(self.latest_results_directory, 'results.json'), 'r') as f:
        #Load json file into results object
        self.results = json.load(f)
    except IOError:
      logging.warn("results.json for test %s not found.",self.name) 
    
    if self.results == None:
      self.results = dict()
      self.results['name'] = self.name
      self.results['concurrencyLevels'] = self.concurrency_levels
      self.results['queryIntervals'] = self.query_levels
      self.results['frameworks'] = [t.name for t in self.__gather_tests]
      self.results['duration'] = self.duration
      self.results['rawData'] = dict()
      self.results['rawData']['json'] = dict()
      self.results['rawData']['db'] = dict()
      self.results['rawData']['query'] = dict()
      self.results['rawData']['fortune'] = dict()
      self.results['rawData']['update'] = dict()
      self.results['rawData']['plaintext'] = dict()
      self.results['completed'] = dict()
      self.results['succeeded'] = dict()
      self.results['succeeded']['json'] = []
      self.results['succeeded']['db'] = []
      self.results['succeeded']['query'] = []
      self.results['succeeded']['fortune'] = []
      self.results['succeeded']['update'] = []
      self.results['succeeded']['plaintext'] = []
      self.results['failed'] = dict()
      self.results['failed']['json'] = []
      self.results['failed']['db'] = []
      self.results['failed']['query'] = []
      self.results['failed']['fortune'] = []
      self.results['failed']['update'] = []
      self.results['failed']['plaintext'] = []
      self.results['verify'] = dict()
    else:
      #for x in self.__gather_tests():
      #  if x.name not in self.results['frameworks']:
      #    self.results['frameworks'] = self.results['frameworks'] + [x.name]
      # Always overwrite framework list
      self.results['frameworks'] = [t.name for t in self.__gather_tests]

    # Setup the ssh command string
    self.database_ssh_string = "ssh -T -o StrictHostKeyChecking=no " + self.database_user + "@" + self.database_host
    self.client_ssh_string = "ssh -T -o StrictHostKeyChecking=no " + self.client_user + "@" + self.client_host
    if self.database_identity_file != None:
      self.database_ssh_string = self.database_ssh_string + " -i " + self.database_identity_file
    if self.client_identity_file != None:
      self.client_ssh_string = self.client_ssh_string + " -i " + self.client_identity_file

    # If we are the master, turn on the load generation container
    # TODO eventually this should only happen if mode==benchmark
    if self.docker and not self.docker_client:
      print "Starting docker client!"
      c = setup_util.get_client()

      # Ensure container is built
      repo="%s/tfb-client" % subprocess.check_output("printf $USER", shell=True)
      if not setup_util.exists(repo):
        path = self.fwroot + '/toolset/setup/docker/client'
        print "DOCKER: No client container, building %s (cwd=%s)" % (repo,path)
        for line in c.build(path=path, tag=repo, stream=True, quiet=False, rm=True):
          setup_util.print_json_stream(line)
        print "DOCKER: Built %s" % repo

      # Ensure tfb-client is not already running
      for container in c.containers():
        if container['Image'].startswith(repo):
          print "DOCKER: ERROR - Container %s already running. Killing" % repo
          c.stop(container, timeout=15)

      # Run container
      #
      # Note: Container will vacuum up any public key files from /tmp/zz_ssh
      #       and set them up for passwordless SSH access, so all we have to 
      #       do here is mount the folder containing our public key files. We
      #       assume that's the folder where the client_identity_file is from
      #
      print "DOCKER: Starting %s" % repo
      client = c.create_container(repo, volumes=[ '/tmp/zz_ssh' ])
      key_dir = os.path.abspath(os.path.dirname(os.path.expanduser(self.client_identity_file)))
      print "DOCKER: Client will search %s for public keys" % key_dir
      mounts={
        key_dir : { 'bind': '/tmp/zz_ssh' }, 
      }
      
      lxc_options = {}
      if self.docker_client_cpuset:
        lxc_options['lxc.cgroup.cpuset.cpus'] = ",".join(str(x) for x in self.docker_client_cpuset)
        print "DOCKER: Client allowing processors [%s]" % lxc_options['lxc.cgroup.cpuset.cpus']
        
        # Update threads to be correct e.g. run wrk with threads == client logical processors
        self.threads = len(self.docker_client_cpuset)

        # Update max_threads (whcih is used only by frameworks) to be correct == logical processors 
        # allowed for this server
        self.max_threads = len(self.docker_server_cpuset)

        print "DOCKER: Updated `threads` to %s and `max_threads` to %s" % (self.threads, self.max_threads)
      if self.docker_client_ram:
        # Set (swap+ram)==(ram) to disable swap
        # See http://stackoverflow.com/a/26482080/119592
        if self.docker_client_ram < 800:
          print "DOCKER: ERROR: wrk requires at least 800MB of RAM. Increasing %s to 850" % self.docker_client_ram
          self.docker_client_ram = 850
          print "DOCKER: WARNING: If you are running wrk and the server on the same host, be sure you have enough mem for both!"
        lxc_options['lxc.cgroup.memory.max_usage_in_bytes']= "%sM" % self.docker_client_ram
        lxc_options['lxc.cgroup.memory.limit_in_bytes']    = "%sM" % self.docker_client_ram
        print "DOCKER: Client allowing %s MB real RAM" % self.docker_client_ram
      lxc = " ".join([ "--lxc-conf=\"%s=%s\""%(k,v) for k,v in lxc_options.iteritems()])
      d_command = "sudo docker run -d %s --net=host -v %s:/tmp/zz_ssh %s" % (lxc, key_dir, repo)
      
      print "DOCKER: Running client container using:"
      print "DOCKER: %s" % d_command
      c.start(client, binds=mounts, network_mode='host', lxc_conf=lxc_options)

      # Update SSH connection string 
      #   Client container uses u/p root:root and port 2332 
      self.client_ssh_string = "ssh -T -o StrictHostKeyChecking=no root@localhost -p 2332"
      self.client_ssh_string += " -i " + self.client_identity_file

      print "DOCKER: Master will use client SSH string %s" % self.client_ssh_string

      self.docker_client_container = client
    elif self.docker_client:
      # If we are running inside the server container, update the client SSH 
      # string to include the port. Note that the client is started from 
      # the server container, which has a mount containing the client_identity_file
      self.client_ssh_string = "ssh -T -o StrictHostKeyChecking=no root@localhost -p 2332"
      self.client_ssh_string += " -i " + self.client_identity_file
      print "DOCKER: Server will use client SSH string %s" % self.client_ssh_string

        
    if self.install is not None:
      install = Installer(self, self.install_strategy, self.docker)
      install.install_software()

  ############################################################
  # End __init__
  ############################################################

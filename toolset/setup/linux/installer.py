import subprocess
import os
import os.path
import time
import traceback
import sys
import glob
import logging
import setup_util

from benchmark.utils import gather_tests

class Installer:

  ############################################################
  # install_software
  ############################################################
  def install_software(self):
    linux_install_root = self.fwroot + "/toolset/setup/linux"
    imode = self.benchmarker.install

    if imode == 'all' or imode == 'server':
      self.__install_server_software()

    if imode == 'all' or imode == 'database':
      print("\nINSTALL: Installing database software\n")   
      self.__run_command("cd .. && " + self.benchmarker.database_sftp_string(batch_file="../config/database_sftp_batch"), True)
      with open (linux_install_root + "/database.sh", "r") as myfile:
        remote_script=myfile.read().format(database_host=self.benchmarker.database_host)
        print("\nINSTALL: %s" % self.benchmarker.database_ssh_string)
        p = subprocess.Popen(self.benchmarker.database_ssh_string.split(" ") + ["bash"], stdin=subprocess.PIPE)
        p.communicate(remote_script)
        returncode = p.returncode
        if returncode != 0:
          self.__install_error("status code %s running subprocess '%s'." % (returncode, self.benchmarker.database_ssh_string))
      print("\nINSTALL: Finished installing database software\n")

    if imode == 'all' or imode == 'client':
      print("\nINSTALL: Installing client software\n")    
      with open (linux_install_root + "/client.sh", "r") as myfile:
        remote_script=myfile.read()
        print("\nINSTALL: %s" % self.benchmarker.client_ssh_string)
        p = subprocess.Popen(self.benchmarker.client_ssh_string.split(" ") + ["bash"], stdin=subprocess.PIPE)
        p.communicate(remote_script)
        returncode = p.returncode
        if returncode != 0:
          self.__install_error("status code %s running subprocess '%s'." % (returncode, self.benchmarker.client_ssh_string))
      print("\nINSTALL: Finished installing client software\n")
  ############################################################
  # End install_software
  ############################################################

  def __setup_prequesites_container(self):
    # import docker here

    c = setup_util.get_client()

    # Ensure we have setup initial image with prerequisites
    user = subprocess.check_output("printf $USER", shell=True)
    tag="%s/tfb-prerequisites" % user
    if not setup_util.exists(tag):
      # Always build from local system
      print "DOCKER: No prerequisites container, building %s" % tag
      
      # First clean our directory (no need for multi-GB container)
      # Note that .dockerignore files are not processed by docker-py, so we're adding all 
      # 300MB of .git to the container for now, and it's completely unused


      # TODO - warn that your private config is being included in the prerequisites container

      
      self.__run_command("git ls-files --others --ignored --exclude-standard | grep -v benchmark.cfg | xargs rm -rf", cwd=self.fwroot)
      # Note: There is a bug in git on Ubuntu12.04 that ls-files not list a number of biggies, so 
      # manually clean the big stuff
      self.__run_command("rm -rf installs", cwd=self.fwroot)
      
      print "DOCKER: Tarring context...expect 5-10 minute wait"
      for line in c.build(path=self.fwroot, tag=tag, stream=True, quiet=False, rm=True):
        setup_util.print_json_stream(line)

      if not setup_util.exists(tag):
        raise Exception("DOCKER: Failed to build %s, unable to continue" % tag)
    
    print "DOCKER: Prerequisites container ready"

  def __install_server_software_in_container(self, test_dir):
    
    # Create a name like "erlang-elli"
    test_dir_name = os.path.relpath(test_dir, self.fwroot)[11:].replace('/','-').lower()

    # Need to find one test name that we can reference during the 
    # installation
    tests = gather_tests(include=self.benchmarker.test, 
      exclude=self.benchmarker.exclude,
      benchmarker=self.benchmarker)
    test_name = [t for t in tests if t.directory == test_dir][0].name

    # import docker here
    c = setup_util.get_client()

    # Check cache before build image
    user = subprocess.check_output("printf $USER", shell=True)
    repo="%s/tfb-%s" % (user, test_dir_name)
    if setup_util.exists(repo):
      print "DOCKER: Image %s exists, using cache" % repo
      return
    print "DOCKER: Building %s" % repo

    # Create container to install this test
    #
    #   - base on prerequisites container
    #   - command is installation command
    #   - mount this test's directory inside container so updates 
    #     are detected and included in build
    #   - mount toolset directory in case you're a developer making
    #     changes to that
    prerequisites="%s/tfb-prerequisites" % user
    command="toolset/run-tests.py --install server --test %s --install-error-action abort --install-only --docker-client --verbose" % test_name
    testvolume="/root/FrameworkBenchmarks/%s" % os.path.relpath(test_dir, self.fwroot)
    toolvolume="/root/FrameworkBenchmarks/toolset"
    install_container = c.create_container(prerequisites, command=command, 
      volumes=[testvolume, toolvolume])
    cid = install_container['Id']
    
    # Run the installation
    print "DOCKER: Running install in %s" % cid
    print "DOCKER: Install command is %s" % command
    tool_dir = "%s/toolset" % self.fwroot
    c.start(cid, binds={
      test_dir: { 'bind': testvolume}, 
      tool_dir: { 'bind': toolvolume}
      })

    # Fetch container output while we are running
    while setup_util.is_running(cid):
      output = c.attach(cid, stream=True)
      for line in output:
        # TODO: Occasionally there is a bug with the output generator 
        # and it hangs indefinitely
        print "DOCKER:tfb-%s: %s" % (test_dir_name, line.strip())
      print "Looping for output..."
      time.sleep(100.0 / 1000.0) # Sleep 100ms

    # Check container exit code
    exit = c.wait(cid)
    if exit is not 0: 
      self.__install_error("DOCKER: Non-zero exit when installing %s in %s, expect failures" % (test_name, cid))
      self.__install_error("DOCKER: Storing %s in %s for you to review" % (test_name, "xx-%s" % repo))
      c.commit(cid, repository="xx-%s"%repo, tag='latest', message='Auto-generated by FrameworkBenchmarks')
    else:
      print "DOCKER:tfb-%s: Committing %s as %s" % (test_dir_name, cid, repo)
      c.commit(cid, repository=repo, tag='latest', message='Auto-generated by FrameworkBenchmarks')
      
      # Ensure the commit was able to go through (e.g. enough disk space)
      print "DOCKER:tfb-%s: Checking commit worked"
      if not setup_util.exists(repo):
        self.__install_error("DOCKER: Failed to commit %s (Out of drive space?)" % repo)

    # Cleanup intermediate container
    c.remove_container(cid)

  ############################################################
  # __install_server_software
  ############################################################
  def __install_server_software(self):
    print("\nINSTALL: Installing server software (strategy=%s)\n"%self.strategy)
    # Install global prerequisites
    if self.docker: 
      self.__setup_prequesites_container()
    else:   
      # Install global prerequisites
      bash_functions_path='$FWROOT/toolset/setup/linux/bash_functions.sh'
      prereq_path='$FWROOT/toolset/setup/linux/prerequisites.sh'
      self.__run_command(". %s && . %s" % (bash_functions_path, prereq_path))

    tests = gather_tests(include=self.benchmarker.test, 
      exclude=self.benchmarker.exclude,
      benchmarker=self.benchmarker)
    
    dirs = [t.directory for t in tests]

    # Locate all installation files
    install_files = glob.glob("%s/*/install.sh" % self.fwroot)
    install_files.extend(glob.glob("%s/frameworks/*/*/install.sh" % self.fwroot))

    # Run install for selected tests
    for test_install_file in install_files:
      test_dir = os.path.dirname(test_install_file)
      test_rel_dir = os.path.relpath(test_dir, self.fwroot)
      logging.debug("Considering install of %s (%s, %s)", test_install_file, test_rel_dir, test_dir)

      if test_dir not in dirs:
        continue

      logging.info("Running installation for directory %s (cwd=%s)", test_dir, test_dir)

      # Collect the tests in this directory
      # local_tests = [t for t in tests if t.directory == test_dir]

      if self.docker: 
        self.__install_server_software_in_container(test_dir)
        continue

      # Find installation directory 
      #   e.g. FWROOT/installs or FWROOT/installs/pertest/<test-name>
      test_install_dir="%s/%s" % (self.fwroot, self.install_dir)
      if self.strategy is 'pertest':
        test_install_dir="%s/pertest/%s" % (test_install_dir, test_dir)
      if not os.path.exists(test_install_dir):
        os.makedirs(test_install_dir)
      
      # Move into the proper working directory
      previousDir = os.getcwd()
      os.chdir(test_dir)

      # Load profile for this installation
      profile="%s/bash_profile.sh" % test_dir
      if not os.path.exists(profile):
        logging.warning("Directory %s does not have a bash_profile"%test_dir)
        profile="$FWROOT/config/benchmark_profile"
      else:
        logging.info("Loading environment from %s (cwd=%s)", profile, test_dir)
      setup_util.replace_environ(config=profile, 
        command='export TROOT=%s && export IROOT=%s' %
        (test_dir, test_install_dir))

      # Run test installation script
      #   FWROOT - Path of the FwBm root
      #   IROOT  - Path of this test's install directory
      #   TROOT  - Path to this test's directory 
      self.__run_command('''
        export TROOT=%s && 
        export IROOT=%s && 
        source %s && 
        source %s''' % 
        (test_dir, test_install_dir, 
          bash_functions_path, test_install_file),
          cwd=test_install_dir)

      # Move back to previous directory
      os.chdir(previousDir)

    self.__run_command("sudo apt-get -y autoremove", cwd=self.fwroot);    

    print("\nINSTALL: Finished installing server software\n")
  ############################################################
  # End __install_server_software
  ############################################################

  ############################################################
  # __install_error
  ############################################################
  def __install_error(self, message):
    print("\nINSTALL ERROR: %s\n" % message)
    if self.benchmarker.install_error_action == 'abort':
      sys.exit("Installation aborted.")
  ############################################################
  # End __install_error
  ############################################################

  ############################################################
  # __run_command
  ############################################################
  def __run_command(self, command, send_yes=False, cwd=None, retry=False):
    if cwd is None: 
        cwd = self.install_dir

    if retry:
      max_attempts = 5
    else:
      max_attempts = 1
    attempt = 1
    delay = 0
    if send_yes:
      command = "yes yes | " + command
        
    rel_cwd = setup_util.path_relative_to_root(cwd)
    print("INSTALL: %s (cwd=$FWROOT%s)" % (command, rel_cwd))

    while attempt <= max_attempts:
      error_message = ""
      try:

        # Execute command.
        subprocess.check_call(command, shell=True, cwd=cwd, executable='/bin/bash')
        break  # Exit loop if successful.
      except:
        exceptionType, exceptionValue, exceptionTraceBack = sys.exc_info()
        error_message = "".join(traceback.format_exception_only(exceptionType, exceptionValue))

      # Exit if there are no more attempts left.
      attempt += 1
      if attempt > max_attempts:
        break

      # Delay before next attempt.
      if delay == 0:
        delay = 5
      else:
        delay = delay * 2
      print("Attempt %s/%s starting in %s seconds." % (attempt, max_attempts, delay))
      time.sleep(delay)

    if error_message:
      self.__install_error(error_message)
  ############################################################
  # End __run_command
  ############################################################

  ############################################################
  # __init__(benchmarker)
  ############################################################
  def __init__(self, benchmarker, install_strategy, using_docker):
    self.benchmarker = benchmarker
    self.install_dir = "installs"
    self.fwroot = benchmarker.fwroot
    self.strategy = install_strategy
    self.docker = using_docker
    
    # setup logging
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    try:
      os.mkdir(self.install_dir)
    except OSError:
      pass
  ############################################################
  # End __init__
  ############################################################

# vim: sw=2

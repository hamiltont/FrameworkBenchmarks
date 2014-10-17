import re
import os
import subprocess
import platform
import docker

# Replaces all text found using the regular expression to_replace with the supplied replacement.
def replace_text(file, to_replace, replacement):
    with open(file, "r") as conf:
        contents = conf.read()
    replaced_text = re.sub(to_replace, replacement, contents)
    with open(file, "w") as f:
        f.write(replaced_text)

# Replaces the current process environment with the one found in 
# config file. Retains a few original vars (HOME,PATH, etc) by default. 
# Optionally allows specification of a command to be run before loading
# the environment, to allow the framework to set environment variables
# Note: This command *cannot* print to stdout!
#
# Note: This will not replace the sudo environment (e.g. subprocess.check_call("sudo <command>")). 
# If you must use sudo, consider sudo sh -c ". <config> && your_command"
def replace_environ(config=None, root=None, print_result=False, command='true'):

    if platform.system().lower() == 'windows':

        pass

    else:
    
        # Clean up our current environment, preserving some important items
        mini_environ = {}
        for envname in ['HOME', 'PATH', 'USER', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'FWROOT', 'TRAVIS']:
          if envname in os.environ:
            mini_environ[envname] = os.environ[envname]
        for key in os.environ:
          if key.startswith(('TFB_', 'TRAVIS_')):    # Any TFB_* and TRAVIS_* variables are preserved
            mini_environ[key] = os.environ[key]
        os.environ.clear()

        # Use FWROOT if explicitely provided
        if root is not None: 
          mini_environ['FWROOT']=root
        

        # Run command, source config file, and store resulting environment
        setup_env = "%s && . %s && env" % (command, config)
        env = ""
        try:
            env = subprocess.check_output(setup_env, shell=True, env=mini_environ,
           executable='/bin/bash')
        except subprocess.CalledProcessError:
            # Ensure that an error here does not crash the toolset
            print "CRITICAL: Loading %s returned non-zero exit" % config
            for key,value in mini_environ.iteritems():
                os.environ[key]=value
            return
        for line in env.split('\n'):
            try:
                key, value = line.split('=', 1)
                # If we already have this TFB_ variable, do not overwrite
                if key.startswith('TFB_') and key in mini_environ:
                    os.environ[key]=mini_environ[key]
                else:
                    os.environ[key]=value    
            except:
                if not line: # Don't warn for empty line
                    continue 
                print "WARN: Line '%s' from '%s' is not an environment variable" % (line, config)
                continue
        if print_result:
            out = subprocess.check_output('env', shell=True, executable='/bin/bash')
            print "Environment after loading %s" %config
            print out

# Queries the shell for the value of FWROOT
def get_fwroot():

    if platform.system().lower() == 'windows':

        fwroot = "C:\FrameworkBenchmarks"
        return fwroot

    else:
    
        try:
            # Use printf to avoid getting a newline
            # Redirect to avoid stderr printing
            fwroot = subprocess.check_output('printf $FWROOT 2> /dev/null', shell=True, executable='/bin/bash')
            return fwroot
        except subprocess.CalledProcessError:
            # Make a last-guess effort ;-)
            return os.getcwd();

# Turns absolute path into path relative to FWROOT
# Assumes path is underneath FWROOT, not above
# 
# Useful for clean presentation of paths 
# e.g. /foo/bar/benchmarks/go/bash_profile.sh
# v.s. FWROOT/go/bash_profile.sh 
def path_relative_to_root(path):
    # Requires bash shell parameter expansion
    return subprocess.check_output("D=%s && printf \"${D#%s}\""%(path, get_fwroot()), shell=True, executable='/bin/bash')

##########################################################
#
#  Move these all to docker-utils
#
##########################################################

import json

def get_client(): 
    c = docker.Client(base_url='http://127.0.0.1:4243',
                  version='1.12',
                  timeout=60)
    # c = docker.Client(base_url='http://127.0.0.1:4243',version='1.12',timeout=10)
    # cont=c.create_container('ubuntu', command='echo hello')
    # c.start(cont['Id'])
    return c

def print_json_stream(string):
    line=json.loads(string)
    if 'stream' in line.keys():
        for unique_line in line['stream'].strip().split('\n'):
            print "DOCKER: %s" % unique_line.strip()
    if 'error' in line.keys():
        print "DOCKER:   %s" % line['error'].strip()

def is_running(container_id):
    c = get_client()
    for container in c.containers():
        if container['Id'].startswith(container_id):
            return True
    return False

# Checks if you are currently inside a docker container
# safe to call even if you have not done 'import docker'
def inside_container():
    # Using http://stackoverflow.com/a/23558932/119592
    try:
        lines=subprocess.check_output("cat /proc/1/cgroup | grep docker | wc -l", shell=True)

        if lines.strip() == "0":
            return False
        return True
    except: 
        return False

# Returns True if image exists with given tag
def exists(image=None):
    c = docker.Client(base_url='http://127.0.0.1:4243',
                  version='1.12',
                  timeout=60)
    images = c.images(image)
    return len(images) > 0


# Launches container, runs command, saves new image
def run_in_container(cid, command):
   c.create_container(image, command=None, hostname=None, user=None,
                   detach=False, stdin_open=False, tty=False, mem_limit=0,
                   ports=None, environment=None, dns=None, volumes=None,
                   volumes_from=None, network_disabled=False, name=None,
                   entrypoint=None, cpu_shares=None, working_dir=None,
                   memswap_limit=0)

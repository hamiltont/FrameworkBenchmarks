FROM ubuntu:14.04

# Work around docker issue #2424
RUN locale-gen en_US.UTF-8  
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en  
ENV LC_ALL en_US.UTF-8

# Avoid warning messages from debconf
RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Add python, curl
RUN apt-get update
RUN apt-get install -y python python-minimal python2.7-minimal curl

# Run ADD last so we can cache above commands
ENV HOME /root
ADD . /root/FrameworkBenchmarks/

# Ensure that any config is deleted
RUN rm -f /root/FrameworkBenchmarks/benchmark.cfg

WORKDIR /root/FrameworkBenchmarks
ENV FWROOT /root/FrameworkBenchmarks

# Add pip and install all required python packages
RUN curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | sudo python2.7
RUN pip install -r /root/FrameworkBenchmarks/config/python_requirements.txt

# LXC execution driver requires folders to be created inside the container
# before you can mount into them, so create the containers that we will use
# when we actually run tests
RUN mkdir /tmp/zz_ssh

# Trigger prereq installation into localhost
RUN toolset/run-tests.py --install server --test ''

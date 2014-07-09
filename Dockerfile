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

# Add pip and docker-py
RUN curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | sudo python2.7
RUN pip install docker-py

# Run ADD last so we can cache above commands
ENV HOME /root
ADD . /root/FrameworkBenchmarks/

# Ensure that any config is deleted
RUN rm -f /root/FrameworkBenchmarks/benchmark.cfg

WORKDIR /root/FrameworkBenchmarks
ENV FWROOT /root/FrameworkBenchmarks

# Trigger prereq installation
RUN toolset/run-tests.py --install server --test ''

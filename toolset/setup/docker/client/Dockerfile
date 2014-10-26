FROM rastasheep/ubuntu-sshd:14.04

# Builds a basic SSH container that can be used to generate client
# load. Main extension from above is to handle SSH keys - we assume 
# the folder holding the --client-identity-file also holds the 
# associated public key. We mount that folder inside the container, and
# use any *.pub files found there to create an authorized_keys files
# 
# We also run SSH on a really weird port, in assumption that we will 
# use --net=host when this is run and therefore cannot have any 
# port conflicts
#
# User/pass is root/root

# LXC execution driver requires folders to be created inside the container
# before you can mount into them
RUN mkdir /tmp/zz_ssh

# Setup SSH for passwordless login
RUN echo "AuthorizedKeysFile /root/.ssh/authorized_keys" >> /etc/ssh/sshd_config
RUN mkdir /root/.ssh && \
    touch /root/.ssh/authorized_keys && \
    chown -R root:root /root/.ssh && \
    chmod 700 /root/.ssh && \
    chmod 600 /root/.ssh/authorized_keys

# Make SSHD use an odd port
RUN sed -i 's/Port 22/Port 2332/g' /etc/ssh/sshd_config

# Download git
RUN apt-get update && apt-get install -y git-core

# Set this machine up as a client
# Note: At a later point a better solution would be to bind mount
#       the current project folder and run client.sh from that...
ENV HOME /root
RUN cd ~ && \
    git clone https://github.com/TechEmpower/FrameworkBenchmarks.git && \
    cp FrameworkBenchmarks/toolset/setup/linux/client.sh client.sh && \
    sh client.sh && \
    rm -rf FrameworkBenchmarks && \
    rm -f client.sh

# Must do the copy on run to properly setup 
# keys when the user mounts a volume at /tmp/zz_ssh
CMD for k in `ls /tmp/zz_ssh/*.pub`; do cat $k >> /root/.ssh/authorized_keys; done && \
    /usr/sbin/sshd -D -e
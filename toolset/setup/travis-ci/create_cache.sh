#!/bin/bash

# Trick the installer
export FWROOT=$(pwd)
export IROOT=/tfb-cache/installs

# Bring in the fw_ functions
source toolset/setup/linux/bash_functions.sh

# Decrypt the encrypted dropbox app configuration
openssl aes-256-cbc -K $encrypted_2062b438454b_key -iv $encrypted_2062b438454b_iv -in .dropbox_uploader.enc -out ~/.dropbox_uploader -d
ls -la ~

# cd into IROOT
sudo mkdir -p $IROOT
sudo chown -R $USER:$USER /tfb-cache
cd $IROOT

# Install prereq then our target
. $FWROOT/toolset/setup/linux/prerequisites.sh
fw_depends $1

# Don't make the installs directory indicate this is 
# installed, because it won't be for other workers ;-)
rm -f fwbm_prereqs_installed

# Name the tar dependency-commit.tar.gz e.g. perl-cad7a6e919a3285c6e1d6789929b1ed1e7c66fa2.tar.gz
name=$1-${TRAVIS_COMMIT}.tar.gz

# Create the resulting tar file
echo Creating $name
cd /tfb-cache
tar cf $name $IROOT

# Upload tar file
curl "https://raw.githubusercontent.com/andreafabrizi/Dropbox-Uploader/master/dropbox_uploader.sh" -o dropbox_uploader.sh
chmod a+x dropbox_uploader.sh
./dropbox_uploader.sh -f ~/.dropbox_uploader -p upload $name /

# Print share link to console
./dropbox_uploader.sh -f ~/.dropbox_uploader -p share $name
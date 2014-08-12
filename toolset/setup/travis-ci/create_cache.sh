#!/bin/bash

# Trick the installer
export FWROOT=/tfb-cache
export IROOT=/tfb-cache/installs

# Bring in the fw_ functions
source toolset/setup/linux/bash_functions.sh

# Decrypt the encrypted dropbox app configuration
openssl aes-256-cbc -K $encrypted_2062b438454b_key -iv $encrypted_2062b438454b_iv -in .dropbox_uploader.enc -out ~/.dropbox_uploader -d
ls -la ~

# Run the installation
sudo mkdir -p $IROOT
sudo chown -R $USER:$USER $FWROOT
cd $IROOT
fw_depends $1

# Name the tar dependency-commit.tar.gz e.g. perl-21341234123412341234.tar.gz
name=$1-${TRAVIS_COMMIT}.tar.gz
echo using $name

# Create the resulting tar file
cd $FWROOT
tar cvf $name $IROOT

# Upload tar file
curl "https://raw.githubusercontent.com/andreafabrizi/Dropbox-Uploader/master/dropbox_uploader.sh" -o dropbox_uploader.sh
chmod a+x dropbox_uploader.sh
./dropbox_uploader.sh -f ~/.dropbox_uploader -p upload $name /

# Print share link to console
./dropbox_uploader.sh -f ~/.dropbox_uploader -p share $name
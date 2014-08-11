#!/bin/bash
#
# Our travis setup relies heavily on rapidly cancelling 

# Change as needed...
export FWROOT=/localhdd
export IROOT=/localhdd/installs

source /localhdd/toolset/setup/linux/bash_functions.sh


mk_cache() {
  rm -rf $IROOT
  mkdir -p $IROOT
  fw_depends "$@"
  
}



 && fw_depends perl
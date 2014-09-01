#!/bin/bash

if [ $# != 2 ] ; then 
  echo "Usage: ./test_pull_request.sh <number> <folder>"
  echo ""
  echo " Example: ./test_pull_request.sh 1075 \"Ur/urweb\""
fi

PR=$1
DIR=$2

echo "Bringing up your development virtual machine"
vagrant up

echo "Reverting your virtual machine to the latest snapshot"
vagrant snap rollback

echo "Cloning the pull request"
vagrant ssh -c "mkdir $1 && git clone --depth=50 https://github.com/TechEmpower/FrameworkBenchmarks.git $1 && cd $1 && git fetch origin +refs/pull/$1/merge: && git checkout -qf FETCH_HEAD"

echo "Installing your test"
vagrant ssh -c "cd $1 && toolset/run-tests.py --install server --install-only"

echo "Running your test"
vagrant ssh -c "cd $1 && toolset/run-tests.py --mode verify --filter directory:=$2"


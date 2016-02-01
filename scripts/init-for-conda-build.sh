#!/bin/bash

BNL_URL=https://pergamon.cs.nsls2.local:8443/api
PUBLIC_URL=https://api.anaconda.org

if [ ! $BNL == '' ]; then
  URL=$BNL_URL
else
  URL=$PUBLIC_URL
fi
# make sure that the ramdisk_dir env var exists
# if not, default to ~/ramdisk
if [ "$RAMDISK_DIR" == "" ]; then
  RAMDISK_DIR="$HOME/ramdisk"
  echo "RAMDISK_DIR set to $RAMDISK_DIR"
else
  echo "RAMDISK_DIR already exists at $RAMDISK_DIR"
fi

# if the ramdisk dir does not already exist, then create a ramdisk!
if [ ! -d "$RAMDISK_DIR" ]; then
  mkdir "$RAMDISK_DIR"
  chmod 777 "$RAMDISK_DIR"
  sudo mount -t tmpfs -o size=10G tmpfs "$RAMDISK_DIR"
fi

if [ "$CONDA_DIR" == "" ]; then
  CONDA_DIR="$RAMDISK_DIR/mc"
fi
if [ ! -d "$CONDA_DIR" ]; then
  # check and see if we have a miniconda bash script available
  find ~/Downloads -iname *miniconda* -print | head -n 1 | xargs -I {} bash {} -b -p $CONDA_DIR
  # if conda dir still doesn't exist, download and install
  if [ ! -d "$CONDA_DIR" ]; then
    MC_PATH=~/Downloads/miniconda.sh
    echo Dowloading miniconda to $MC_PATH
    wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -O $MC_PATH
    bash "$MC_PATH" -b -p "$CONDA_DIR"
  fi
fi
# set up a condabuildrc file
echo "
RAMDISK_DIR=$RAMDISK_DIR
CONDA_DIR=$CONDA_DIR
CONDARC=$RAMDISK_DIR/.condarc
source activate $CONDA_DIR
anaconda config --set url $URL" > ~/.condabuildrc
# set up a custom condarc for the ramdisk env
echo "
channels:
 - nsls2-dev
 - nsls2
 - anaconda
always_yes: true
show_channel_urls: true" > "$RAMDISK_DIR/.condarc"

which conda

source ~/.condabuildrc

conda install conda-build anaconda-client --yes
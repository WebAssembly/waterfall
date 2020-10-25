#!/bin/bash
#
# Create a linux sysroot image (tar archive) based on debian
# This is than used in the build scripts as the --sysroot arguments
# when compiling linux binaries.
#
# See https://xw.is/wiki/Create_Debian_sysroots

set -e

SUITE=stretch
TARGET_DIR=sysroot_debian_${SUITE}_amd64

mkdir $TARGET_DIR

# Perform minimal installation
debootstrap $SUITE $TARGET_DIR http://deb.debian.org/debian

# Install additional packages
chroot $TARGET_DIR apt-get install -y -q libstdc++-6-dev

# Convert absolute symlinks to relative
find $TARGET_DIR -type l -lname '/*' -exec sh -c 'file="$0"; dir=$(dirname "$file"); target=$(readlink "$0"); prefix=$(dirname "$dir" | sed 's@[^/]*@\.\.@g'); newtarget="$prefix$target"; echo ln -snf $newtarget $file' {} \;

# Remove parts that are not relevent to --sysroot
for d in dev proc tmp home run var boot media sys srv mnt; do
  rm -rf $TARGET_DIR/$d
done

tar cJf sysroot_debian_${SUITE}_amd64.tar.xz -C $TARGET_DIR .

gsutil cp sysroot_debian_${SUITE}_amd64.tar.xz gs://wasm/

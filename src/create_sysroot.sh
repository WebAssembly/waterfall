#!/bin/bash
#
# Create a linux sysroot image (tar archive) based on debian
# This is than used in the build scripts as the --sysroot arguments
# when compiling linux binaries.
#
# See https://xw.is/wiki/Create_Debian_sysroots
#
# Once created the sysroot should be uploaded to google storage.
# e.g:
#  gsutil cp sysroot_debian_stretch_amd64.tar.xz gs://wasm/

set -o errexit

SUITE=stretch
TARGET_DIR=sysroot_debian_${SUITE}_amd64
VERSION=2

mkdir $TARGET_DIR

# Perform minimal installation
debootstrap $SUITE $TARGET_DIR http://deb.debian.org/debian

# Install additional packages
chroot $TARGET_DIR apt-get install -y -q libstdc++-6-dev zlib1g-dev

# Convert absolute symlinks to relative
find $TARGET_DIR -type l -lname '/*' -exec sh -c 'file="$0"; dir=$(dirname "$file"); target=$(readlink "$0"); prefix=$(dirname "$dir" | sed 's@[^/]*@\.\.@g'); newtarget="$prefix$target"; ln -snf $newtarget $file' {} \;

# Remove parts that are not relevent to --sysroot
for d in dev proc tmp home run var boot media sys srv mnt; do
  rm -rf $TARGET_DIR/$d
done

tar cJf sysroot_debian_${SUITE}_amd64_v${VERSION}.tar.xz -C $TARGET_DIR .

#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LANG=C
export LC_ALL=C

BASE=http://localhost:5000
PKG=installer.tar.gz

#TMP="$(mktemp -d)"
TMP=/tmp/asahi-install

echo
echo "Bootstrapping installer:"

mkdir -p "$TMP"
cd "$TMP"

echo "  Downloading..."

curl -s -L -O "$BASE/$PKG"

echo "  Extracting..."

tar xf "$PKG"

echo "  Initializing..."
echo

if [ "$USER" != "root" ]; then
    echo "The installer needs to run as root."
    echo "Please enter your sudo password if prompted."
    exec sudo ./install.sh "$@"
else
    exec ./install.sh "$@"
fi

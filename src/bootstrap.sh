#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LANG=C
export LC_ALL=C

export INSTALLER_BASE=http://localhost:5000
export INSTALLER_DATA=http://localhost:5000/data/installer_data.json
export REPO_BASE=https://de.mirror.asahilinux.org
PKG=installer.tar.gz

#TMP="$(mktemp -d)"
TMP=/tmp/asahi-install

echo
echo "Bootstrapping installer:"

mkdir -p "$TMP"
cd "$TMP"

echo "  Downloading..."

curl -s -L -O "$INSTALLER_BASE/$PKG"
curl -s -L -O "$INSTALLER_DATA"

echo "  Extracting..."

tar xf "$PKG"

echo "  Initializing..."
echo

if [ "$USER" != "root" ]; then
    echo "The installer needs to run as root."
    echo "Please enter your sudo password if prompted."
    exec sudo -E ./install.sh "$@"
else
    exec ./install.sh "$@"
fi

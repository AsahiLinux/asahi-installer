#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LANG=C
export LC_ALL=C
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

export INSTALLER_BASE=http://localhost:5000
export INSTALLER_DATA=http://localhost:5000/data/installer_data.json
export REPO_BASE=https://cdn.asahilinux.org
PKG=installer.tar.gz

#TMP="$(mktemp -d)"
TMP=/tmp/asahi-install

echo
echo "Bootstrapping installer:"

mkdir -p "$TMP"
cd "$TMP"

echo "  Downloading..."

curl --no-progress-meter -L -O "$INSTALLER_BASE/$PKG"
curl --no-progress-meter -L -O "$INSTALLER_DATA"

echo "  Extracting..."

tar xf "$PKG"

echo "  Initializing..."
echo

if [ "$USER" != "root" ]; then
    echo "The installer needs to run as root."
    echo "Please enter your sudo password if prompted."
    exec caffeinate -dis sudo -E ./install.sh "$@"
else
    exec caffeinate -dis ./install.sh "$@"
fi

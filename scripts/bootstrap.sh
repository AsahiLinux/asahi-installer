#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LANG=C
export LC_ALL=C

export INSTALLER_BASE=http://localhost:5000
export INSTALLER_DATA=http://localhost:5000/data/installer_data.json
export REPO_BASE=https://cdn.asahilinux.org
PKG=installer.tar.gz

#TMP="$(mktemp -d)"
TMP=/tmp/asahi-install

/bin/echo
/bin/echo "Bootstrapping installer:"

/bin/mkdir -p "$TMP"
/usr/bin/cd "$TMP"

/bin/echo "  Downloading..."

/usr/bin/curl -s -L -O "$INSTALLER_BASE/$PKG"
/usr/bin/curl -s -L -O "$INSTALLER_DATA"

/bin/echo "  Extracting..."

/usr/bin/tar xf "$PKG"

/bin/echo "  Initializing..."
/bin/echo

if [ "$USER" != "root" ]; then
    /bin/echo "The installer needs to run as root."
    /bin/echo "Please enter your sudo password if prompted."
    exec caffeinate -dis sudo -E ./install.sh "$@"
else
    exec caffeinate -dis ./install.sh "$@"
fi
